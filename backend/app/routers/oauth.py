import base64
import hashlib
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, delete, select
from starlette.responses import RedirectResponse

from app import database
from app.config import Settings, get_settings
from app.models import LoginSession, OAuthFlow, OAuthIdentity, WorkspaceUser, utc_now
from app.oauth_providers import (
    Identity,
    Provider,
    authorization_url,
    exchange_code,
    oauth_provider,
)
from app.workspace import (
    COOKIE_NAME,
    WORKSPACE_API,
    auth_rate_limit,
    issue_session,
    require_auth_mode,
    token_hash,
)

router = APIRouter(prefix=f"{WORKSPACE_API}/oauth", tags=["workspace"])
FLOW_COOKIE = "pageindex_oauth"
FLOW_LIFETIME = timedelta(minutes=10)


def _callback_url(settings: Settings, provider: Provider) -> str:
    return f"{settings.app_public_url}{router.prefix}/{provider}/callback"


def _redirect(
    settings: Settings, reason: str | None = None, *, linked: bool = False
) -> RedirectResponse:
    if reason:
        fragment = urlencode({"auth": "oauth-error", "reason": reason})
        destination = f"{settings.app_public_url}/login#{fragment}"
    else:
        route = "account" if linked else "workspace"
        destination = f"{settings.app_public_url}/{route}"
    response = RedirectResponse(
        destination, status_code=303, headers={"Referrer-Policy": "no-referrer"}
    )
    response.delete_cookie(
        FLOW_COOKIE,
        path=router.prefix,
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/{provider}")
def start(provider: Provider, request: Request, link: bool = False) -> RedirectResponse:
    require_auth_mode()
    settings = get_settings()
    if provider not in settings.oauth_providers:
        raise HTTPException(
            status_code=404, detail="This sign-in provider is unavailable"
        )
    session_hash = None
    if link:
        if request.state.workspace is None:
            raise HTTPException(status_code=401, detail="Sign in to connect a provider")
        session_hash = token_hash(request.cookies[COOKIE_NAME])
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "oauth")
        session.exec(delete(OAuthFlow).where(OAuthFlow.expires_at <= utc_now()))
        session.add(
            OAuthFlow(
                state_hash=token_hash(state),
                provider=provider,
                verifier=verifier,
                nonce=nonce,
                session_hash=session_hash,
                expires_at=utc_now() + FLOW_LIFETIME,
            )
        )
        session.commit()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    url = authorization_url(
        oauth_provider(settings, provider),
        provider,
        _callback_url(settings, provider),
        state,
        challenge,
        nonce,
    )
    response = RedirectResponse(
        url, status_code=303, headers={"Referrer-Policy": "no-referrer"}
    )
    response.set_cookie(
        FLOW_COOKIE,
        state,
        path=router.prefix,
        max_age=int(FLOW_LIFETIME.total_seconds()),
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    return response


def _take_flow(provider: Provider, state: str) -> OAuthFlow | None:
    with Session(database.engine) as session:
        flow = session.exec(
            delete(OAuthFlow)
            .where(
                OAuthFlow.state_hash == token_hash(state),
                OAuthFlow.provider == provider,
                OAuthFlow.expires_at > utc_now(),
            )
            .returning(OAuthFlow)
        ).scalar_one_or_none()
        if flow:
            session.expunge(flow)
        session.commit()
        return flow


def _sign_in(
    settings: Settings,
    provider: Provider,
    identity: Identity,
    session_hash: str | None,
    request: Request,
) -> RedirectResponse:
    with Session(database.engine) as session:
        database.lock_auth_transaction(session)
        existing = session.get(OAuthIdentity, (provider, identity.subject))
        if session_hash:
            login = session.get(LoginSession, session_hash)
            if login is None or login.expires_at <= utc_now():
                return _redirect(settings, "session-expired")
            user = session.get(WorkspaceUser, login.user_id)
            if user is None:
                return _redirect(settings, "session-expired")
            already_linked = session.exec(
                select(OAuthIdentity).where(
                    OAuthIdentity.user_id == user.id, OAuthIdentity.provider == provider
                )
            ).first()
            if (existing and existing.user_id != user.id) or (
                already_linked and already_linked.subject != identity.subject
            ):
                return _redirect(settings, "already-linked")
        elif existing:
            user = session.get(WorkspaceUser, existing.user_id)
            if user is None:
                return _redirect(settings, "failed")
        else:
            if session.exec(
                select(WorkspaceUser.id).where(WorkspaceUser.email == identity.email)
            ).first():
                return _redirect(settings, "account-exists")
            if not settings.auth_allow_signup:
                return _redirect(settings, "signup-disabled")
            base = re.sub(r"[^a-z0-9_.-]", "-", identity.email.split("@", 1)[0]).strip(
                "_.-"
            )[:40]
            base = base if len(base) >= 3 else "user"
            user = WorkspaceUser(
                username=f"{base}-{secrets.token_hex(5)}",
                email=identity.email,
                email_verified=True,
            )
            session.add(user)
        response = _redirect(settings, linked=session_hash is not None)
        try:
            if not existing:
                session.flush()
                session.add(
                    OAuthIdentity(
                        provider=provider, subject=identity.subject, user_id=user.id
                    )
                )
            if session_hash:
                session.delete(login)
            issue_session(session, user, request, response)
        except IntegrityError:
            return _redirect(settings, "already-linked")
        return response


@router.get("/{provider}/callback")
def callback(
    provider: Provider,
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    require_auth_mode()
    settings = get_settings()
    cookie_state = request.cookies.get(FLOW_COOKIE, "")
    if (
        provider not in settings.oauth_providers
        or len(state) != 43
        or not secrets.compare_digest(state.encode(), cookie_state.encode())
    ):
        return _redirect(settings, "invalid-state")
    flow = _take_flow(provider, state)
    if flow is None:
        return _redirect(settings, "invalid-state")
    if error or not code:
        return _redirect(settings, "cancelled")
    try:
        identity = exchange_code(
            oauth_provider(settings, provider),
            provider,
            code,
            _callback_url(settings, provider),
            flow.verifier,
            flow.nonce,
        )
    except (
        httpx.HTTPError,
        jwt.PyJWTError,
        ValidationError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        return _redirect(settings, "failed")
    return _sign_in(settings, provider, identity, flow.session_hash, request)
