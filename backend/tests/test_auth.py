import base64
import hashlib
import unittest
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from database_support import test_engine
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine

from app import database
from app.config import Settings
from app.models import EmailLink, WorkspaceUser, utc_now
from app.oauth_providers import Identity
from app.workspace import COOKIE_NAME, WORKSPACE_API, hash_password, token_hash
from main import app


class TestAuthentication(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.settings = Settings(
            _env_file=None,
            auth_required=True,
            secure_cookies=False,
            resend_api_key="test-key",
            resend_from_email="auth@example.com",
            google_client_id="google-id",
            google_client_secret="google-secret",
            github_client_id="github-id",
            github_client_secret="github-secret",
        )
        for name in (
            "app.workspace",
            "app.routers.accounts",
            "app.routers.oauth",
            "main",
        ):
            self.enterContext(patch(f"{name}.get_settings", return_value=self.settings))
        self.engine = test_engine(self, f"sqlite:///{directory}/app.db")
        self.enterContext(patch.object(database, "engine", self.engine))
        self.enterContext(patch.object(database, "database_url", self.engine.url))
        database.create_db_and_tables()
        self.mail = self.enterContext(patch("app.routers.accounts.send_email"))
        self.exchange = self.enterContext(patch("app.routers.oauth.exchange_code"))
        self.client = self.new_client()

    def new_client(self):
        return self.enterContext(
            TestClient(
                app, base_url=self.settings.app_public_url, follow_redirects=False
            )
        )

    def post(self, endpoint, **payload):
        return self.client.post(f"{WORKSPACE_API}/{endpoint}", json=payload)

    def session(self):
        return self.client.get(f"{WORKSPACE_API}/session").json()

    def email_token(self, action):
        link = self.mail.call_args.args[2].text.splitlines()[2]
        url = urlsplit(link)
        self.assertEqual(f"{url.scheme}://{url.netloc}", self.settings.app_public_url)
        self.assertEqual(url.query, "")
        self.assertEqual(
            url.path, "/complete-registration" if action == "signup" else f"/{action}"
        )
        fragment = parse_qs(url.fragment)
        self.assertEqual(fragment["auth"], [action])
        return fragment["token"][0]

    def register(self):
        self.assertEqual(
            self.post("signup", email="Alice@example.com").status_code, 202
        )
        token = self.email_token("signup")
        response = self.post(
            "verify-signup", token=token, username="alice", password="initial-password"
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["email"], "alice@example.com")
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(self.session()["username"], "alice")
        return token

    def add_legacy_user(self):
        with Session(self.engine) as session:
            session.add(
                WorkspaceUser(
                    username="legacy", password_hash=hash_password("legacy-password")
                )
            )
            session.commit()

    def test_signup_verification_is_single_use(self):
        token = self.register()
        response = self.post(
            "verify-signup",
            token=token,
            username="another",
            password="another-password",
        )
        self.assertEqual(response.status_code, 400)
        count = self.mail.call_count
        existing = self.post("signup", email="alice@example.com")
        new = self.post("signup", email="new@example.com")
        self.assertEqual(existing.json(), new.json())
        self.assertEqual(self.mail.call_count, count + 1)

    def test_reset_revokes_sessions_and_pending_links(self):
        self.register()
        other = self.new_client()
        old = {"username": "ALICE@example.com", "password": "initial-password"}
        self.assertEqual(
            other.post(f"{WORKSPACE_API}/login", json=old).status_code, 200
        )
        self.post("forgot-password", email="alice@example.com")
        first = self.email_token("reset-password")
        self.post("forgot-password", email="alice@example.com")
        latest = self.email_token("reset-password")
        self.assertEqual(
            self.post(
                "reset-password", token=latest, password="updated-password"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.mail.call_args.args[2].subject, "Your PageIndex password changed"
        )
        self.assertIsNone(self.session()["username"])
        self.assertIsNone(other.get(f"{WORKSPACE_API}/session").json()["username"])
        self.assertEqual(self.post("login", **old).status_code, 401)
        self.assertEqual(
            self.post(
                "login", username="alice", password="updated-password"
            ).status_code,
            200,
        )
        for token in (first, latest):
            self.assertEqual(
                self.post(
                    "reset-password", token=token, password="another-password"
                ).status_code,
                400,
            )

    def test_expired_link_is_rejected(self):
        self.post("signup", email="alice@example.com")
        token = self.email_token("signup")
        with Session(self.engine) as session:
            link = session.get(EmailLink, token_hash(token))
            link.expires_at = utc_now() - timedelta(minutes=1)
            session.commit()
        self.assertEqual(
            self.post(
                "verify-signup",
                token=token,
                username="alice",
                password="initial-password",
            ).status_code,
            400,
        )

    def test_legacy_account_can_verify_a_recovery_address(self):
        self.add_legacy_user()
        self.assertEqual(
            self.post(
                "account/email", email="legacy@example.com", password="legacy-password"
            ).status_code,
            401,
        )
        self.assertEqual(
            self.post(
                "login", username="legacy", password="legacy-password"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.post(
                "account/email", email="legacy@example.com", password="wrong"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                "account/email", email="legacy@example.com", password="legacy-password"
            ).status_code,
            202,
        )
        token = self.email_token("verify-email")
        self.assertEqual(
            self.post(
                "reset-password", token=token, password="other-password"
            ).status_code,
            400,
        )
        self.assertEqual(self.post("verify-email", token=token).status_code, 200)
        self.assertTrue(self.session()["email_verified"])
        self.assertEqual(self.session()["email"], "legacy@example.com")

    def oauth_start(self, provider, *, link=False):
        response = self.client.get(
            f"{WORKSPACE_API}/oauth/{provider}", params={"link": str(link).lower()}
        )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn("SameSite=lax", response.headers["set-cookie"])
        params = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(
            params["redirect_uri"],
            [
                f"{self.settings.app_public_url}{WORKSPACE_API}/oauth/{provider}/callback"
            ],
        )
        return params

    def oauth_callback(self, provider, state, client=None):
        return (client or self.client).get(
            f"{WORKSPACE_API}/oauth/{provider}/callback",
            params={"state": state, "code": "provider-code"},
        )

    def test_google_signin_checks_browser_state_and_pkce_then_rejects_replay(self):
        self.exchange.return_value = Identity("google-user", "social@example.com")
        params = self.oauth_start("google")
        state = params["state"][0]
        other = self.new_client()
        denied = self.oauth_callback("google", state, client=other)
        self.assertIn("invalid-state", denied.headers["location"])
        self.exchange.assert_not_called()
        response = self.oauth_callback("google", state)
        self.assertEqual(
            response.headers["location"], f"{self.settings.app_public_url}/workspace"
        )
        verifier, nonce = self.exchange.call_args.args[-2:]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        self.assertEqual(params["code_challenge"], [challenge])
        self.assertEqual(params["nonce"], [nonce])
        self.assertEqual(self.session()["linked_providers"], ["google"])
        self.assertFalse(self.session()["has_password"])
        self.assertTrue(self.session()["email_verified"])
        self.assertEqual(self.client.get("/api/v1/documents").json(), [])
        self.client.cookies.set("pageindex_oauth", state, path=f"{WORKSPACE_API}/oauth")
        self.assertIn(
            "invalid-state", self.oauth_callback("google", state).headers["location"]
        )
        self.exchange.assert_called_once()

    def test_github_requires_explicit_account_link_and_preserves_identity(self):
        self.register()
        self.post("logout")
        self.exchange.return_value = Identity("github-user", "alice@example.com")
        params = self.oauth_start("github")
        self.assertIn(
            "account-exists",
            self.oauth_callback("github", params["state"][0]).headers["location"],
        )
        self.assertIsNone(self.session()["username"])
        self.assertEqual(
            self.post(
                "login", username="alice", password="initial-password"
            ).status_code,
            200,
        )
        params = self.oauth_start("github", link=True)
        self.client.cookies.delete(COOKIE_NAME, path="/api/v1")
        self.assertEqual(
            self.oauth_callback("github", params["state"][0]).headers["location"],
            f"{self.settings.app_public_url}/account",
        )
        self.assertEqual(self.session()["linked_providers"], ["github"])
        self.post("logout")
        params = self.oauth_start("github")
        self.oauth_callback("github", params["state"][0])
        self.assertEqual(self.session()["username"], "alice")

    def test_revoked_session_cannot_link_provider(self):
        self.register()
        self.exchange.return_value = Identity("github-user", "social@example.com")
        params = self.oauth_start("github", link=True)
        self.post("logout")
        self.assertIn(
            "session-expired",
            self.oauth_callback("github", params["state"][0]).headers["location"],
        )
        self.assertIsNone(self.session()["username"])

    def test_configuration_and_origin_gate(self):
        self.settings.github_client_id = ""
        self.settings.auth_allow_signup = False
        self.assertEqual(self.session()["oauth_providers"], ["google"])
        self.assertFalse(self.session()["signup_enabled"])
        self.assertFalse(self.session()["registration_open"])
        self.assertEqual(
            self.post("signup", email="alice@example.com").status_code, 403
        )
        self.assertEqual(
            self.client.get(f"{WORKSPACE_API}/oauth/github").status_code, 404
        )
        self.exchange.return_value = Identity("google-user", "new@example.com")
        params = self.oauth_start("google")
        self.assertIn(
            "signup-disabled",
            self.oauth_callback("google", params["state"][0]).headers["location"],
        )
        response = self.client.post(
            f"{WORKSPACE_API}/logout", headers={"Origin": "https://other.example"}
        )
        self.assertEqual(response.status_code, 403)

    def test_existing_database_migrates_accounts_without_losing_users(self):
        url = make_url(f"sqlite:///{self.enterContext(TemporaryDirectory())}/legacy.db")
        engine = create_engine(url)
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE workspaceuser (id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL, password_hash VARCHAR NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO workspaceuser (id, username, password_hash) VALUES (?, ?, ?)",
                ("legacy-id", "legacy-user", hash_password("legacy-password")),
            )
        with (
            patch.object(database, "engine", engine),
            patch.object(database, "database_url", url),
        ):
            database.create_db_and_tables()
            database.create_db_and_tables()
        with Session(engine) as session:
            user = session.get(WorkspaceUser, "legacy-id")
            self.assertEqual(user.username, "legacy-user")
            self.assertIsNone(user.email)
            self.assertFalse(user.email_verified)

    def test_validation_does_not_echo_passwords_or_link_tokens(self):
        response = self.post("reset-password", token="expired-token", password="secret")
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("expired-token", response.text)
        self.assertNotIn("secret", response.text)

    def test_change_password_requires_current_password_and_revokes_all_sessions(self):
        self.register()
        second_client = self.new_client()
        login = {"username": "alice", "password": "initial-password"}
        self.assertEqual(
            second_client.post(f"{WORKSPACE_API}/login", json=login).status_code, 200
        )
        self.post("forgot-password", email="alice@example.com")
        reset = self.email_token("reset-password")
        response = self.post(
            "account/password",
            current_password="wrong",
            new_password="updated-password",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.session()["username"], "alice")
        response = self.post(
            "account/password",
            current_password="initial-password",
            new_password="updated-password",
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(self.session()["username"])
        self.assertIsNone(
            second_client.get(f"{WORKSPACE_API}/session").json()["username"]
        )
        self.assertEqual(
            self.mail.call_args.args[2].subject, "Your PageIndex password changed"
        )
        self.assertEqual(
            self.post(
                "reset-password", token=reset, password="another-password"
            ).status_code,
            400,
        )
        self.assertEqual(self.post("login", **login).status_code, 401)
        login["password"] = "updated-password"
        self.assertEqual(self.post("login", **login).status_code, 200)

    def test_sign_out_everywhere_only_revokes_the_current_accounts_sessions(self):
        self.register()
        self.add_legacy_user()
        second_client = self.new_client()
        other_account = self.new_client()
        login = f"{WORKSPACE_API}/login"
        self.assertEqual(
            second_client.post(
                login, json={"username": "alice", "password": "initial-password"}
            ).status_code,
            200,
        )
        self.assertEqual(
            other_account.post(
                login, json={"username": "legacy", "password": "legacy-password"}
            ).status_code,
            200,
        )
        self.assertEqual(self.post("account/logout-all").status_code, 204)
        self.assertIsNone(self.session()["username"])
        self.assertIsNone(
            second_client.get(f"{WORKSPACE_API}/session").json()["username"]
        )
        self.assertEqual(
            other_account.get(f"{WORKSPACE_API}/session").json()["username"], "legacy"
        )
        self.assertEqual(self.post("account/logout-all").status_code, 401)
