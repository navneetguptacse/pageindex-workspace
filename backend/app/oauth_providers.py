from dataclasses import dataclass
from functools import lru_cache
from secrets import compare_digest
from typing import Literal
from urllib.parse import urlencode

import httpx
import jwt
from pydantic import EmailStr, TypeAdapter

from app.config import Settings

Provider = Literal["google", "github"]
email_adapter = TypeAdapter(EmailStr)


@dataclass(frozen=True)
class OAuthProvider:
    client_id: str
    client_secret: str
    authorization_url: str
    token_url: str
    scopes: str


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str


def oauth_provider(settings: Settings, name: Provider) -> OAuthProvider:
    if name == "google":
        return OAuthProvider(
            settings.google_client_id.strip(),
            settings.google_client_secret.get_secret_value().strip(),
            "https://accounts.google.com/o/oauth2/v2/auth",
            "https://oauth2.googleapis.com/token",
            "openid email",
        )
    return OAuthProvider(
        settings.github_client_id.strip(),
        settings.github_client_secret.get_secret_value().strip(),
        "https://github.com/login/oauth/authorize",
        "https://github.com/login/oauth/access_token",
        "user:email",
    )


def authorization_url(
    provider: OAuthProvider,
    name: Provider,
    redirect_uri: str,
    state: str,
    challenge: str,
    nonce: str,
) -> str:
    params = {
        "client_id": provider.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": provider.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if name == "google":
        params["nonce"] = nonce
    return f"{provider.authorization_url}?{urlencode(params)}"


@lru_cache(maxsize=1)
def google_keys() -> jwt.PyJWKClient:
    return jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", timeout=8)


def _google_identity(token: str, client_id: str, nonce: str) -> Identity:
    key = google_keys().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=["https://accounts.google.com", "accounts.google.com"],
        options={"require": ["sub", "aud", "iss", "exp", "iat", "nonce"]},
    )
    if (
        not isinstance(claims["nonce"], str)
        or not compare_digest(claims["nonce"].encode(), nonce.encode())
        or ("azp" in claims and claims["azp"] != client_id)
        or (
            isinstance(claims["aud"], list)
            and len(claims["aud"]) > 1
            and "azp" not in claims
        )
        or claims.get("email_verified") is not True
    ):
        raise ValueError("Google did not verify this account")
    return Identity(
        claims["sub"], email_adapter.validate_python(claims["email"]).casefold()
    )


def _github_identity(client: httpx.Client, access_token: str) -> Identity:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "PageIndex",
    }
    user = (
        client.get("https://api.github.com/user", headers=headers)
        .raise_for_status()
        .json()
    )
    emails = (
        client.get("https://api.github.com/user/emails", headers=headers)
        .raise_for_status()
        .json()
    )
    primary = next(
        (
            row["email"]
            for row in emails
            if row.get("primary") is True and row.get("verified") is True
        ),
        None,
    )
    if type(user.get("id")) is not int or primary is None:
        raise ValueError("GitHub did not verify a primary email")
    return Identity(str(user["id"]), email_adapter.validate_python(primary).casefold())


def exchange_code(
    provider: OAuthProvider,
    name: Provider,
    code: str,
    redirect_uri: str,
    verifier: str,
    nonce: str,
) -> Identity:
    with httpx.Client(timeout=10) as client:
        tokens = (
            client.post(
                provider.token_url,
                data={
                    "client_id": provider.client_id,
                    "client_secret": provider.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            .raise_for_status()
            .json()
        )
        if name == "google":
            return _google_identity(tokens["id_token"], provider.client_id, nonce)
        return _github_identity(client, tokens["access_token"])
