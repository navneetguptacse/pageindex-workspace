import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.account_email import AccountEmail, EmailDeliveryError, send_email
from app.config import Settings
from app.oauth_providers import (
    Identity,
    _google_identity,
    exchange_code,
    oauth_provider,
)


class TestAuthProviders(unittest.TestCase):
    def test_google_checks_signed_identity_audience_and_nonce(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        claims = {
            "sub": "google-user",
            "iss": "https://accounts.google.com",
            "aud": "pageindex",
            "iat": now,
            "exp": now + timedelta(minutes=1),
            "email": "User@example.com",
            "email_verified": True,
            "nonce": "browser-nonce",
        }
        with patch("app.oauth_providers.google_keys") as keys:
            keys.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(
                key=key.public_key()
            )
            token = jwt.encode(claims, key, algorithm="RS256")
            self.assertEqual(
                _google_identity(token, "pageindex", "browser-nonce"),
                Identity("google-user", "user@example.com"),
            )
            with self.assertRaises(ValueError):
                _google_identity(token, "pageindex", "other-nonce")
            with self.assertRaises(jwt.InvalidAudienceError):
                _google_identity(token, "other-client", "browser-nonce")
            claims["email_verified"] = False
            token = jwt.encode(claims, key, algorithm="RS256")
            with self.assertRaises(ValueError):
                _google_identity(token, "pageindex", "browser-nonce")

    def test_github_uses_pkce_and_verified_primary_email(self):
        settings = Settings(
            _env_file=None, github_client_id="client", github_client_secret="secret"
        )
        verified = True

        def github(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                self.assertEqual(request.url.host, "github.com")
                body = parse_qs(request.content.decode())
                self.assertEqual(body["code_verifier"], ["test-verifier"])
                return httpx.Response(200, json={"access_token": "github-token"})
            self.assertEqual(request.headers["authorization"], "Bearer github-token")
            if request.url.path == "/user":
                return httpx.Response(200, json={"id": 12345})
            return httpx.Response(
                200,
                json=[
                    {
                        "primary": False,
                        "verified": True,
                        "email": "secondary@example.com",
                    },
                    {
                        "primary": True,
                        "verified": verified,
                        "email": "primary@example.com",
                    },
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(github))
        args = (
            oauth_provider(settings, "github"),
            "github",
            "code",
            "http://localhost/callback",
            "test-verifier",
            "",
        )
        with patch("app.oauth_providers.httpx.Client", return_value=client):
            self.assertEqual(
                exchange_code(*args), Identity("12345", "primary@example.com")
            )
        verified = False
        client = httpx.Client(transport=httpx.MockTransport(github))
        with (
            patch("app.oauth_providers.httpx.Client", return_value=client),
            self.assertRaises(ValueError),
        ):
            exchange_code(*args)

    def test_resend_uses_configured_sender_and_handles_failure(self):
        settings = Settings(
            _env_file=None,
            resend_api_key="test-key",
            resend_from_email="auth@example.com",
        )
        destination = "https://api.resend.com/emails"
        with patch("app.account_email.httpx.post") as post:
            post.return_value = httpx.Response(
                200, request=httpx.Request("POST", destination)
            )
            send_email(
                settings,
                "user@example.com",
                AccountEmail("Test", "Verify your account"),
            )
            self.assertEqual(post.call_args.args, (destination,))
            self.assertEqual(
                post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key"
            )
            self.assertEqual(post.call_args.kwargs["json"]["from"], "auth@example.com")
            self.assertEqual(post.call_args.kwargs["json"]["to"], ["user@example.com"])
            post.return_value = httpx.Response(
                429, request=httpx.Request("POST", destination)
            )
            with self.assertRaises(EmailDeliveryError):
                send_email(
                    settings,
                    "user@example.com",
                    AccountEmail("Test", "Verify your account"),
                )
