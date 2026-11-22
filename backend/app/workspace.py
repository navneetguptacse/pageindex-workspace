import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, delete, select
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app import database
from app.config import get_settings
from app.database import SessionDep, Workspace, current_workspace
from app.models import LoginSession, OAuthIdentity, Quota, WorkspaceUser, utc_now
from app.quota import increment_quota

COOKIE_NAME = "pageindex_session"
SESSION_LIFETIME = timedelta(hours=12)
WORKSPACE_API = "/api/v1/workspace"
router = APIRouter(prefix=WORKSPACE_API, tags=["workspace"])
PUBLIC_WORKSPACE_ROUTES = {
    (method, f"{WORKSPACE_API}{path}")
    for method, path in (
        ("GET", "/session"),
        ("POST", "/login"),
        ("POST", "/logout"),
        ("POST", "/signup"),
        ("POST", "/verify-signup"),
        ("POST", "/verify-email"),
        ("POST", "/forgot-password"),
        ("POST", "/reset-password"),
        *(
            ("GET", f"/oauth/{provider}{suffix}")
            for provider in ("google", "github")
            for suffix in ("", "/callback")
        ),
    )
}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1
    )
    return f"{salt}:{digest.hex()}"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _authenticated_workspace(token: str) -> Workspace | None:
    if not token or len(token) != 43:
        return None
    with Session(database.engine) as session:
        login = session.get(LoginSession, token_hash(token))
        if login and login.expires_at > utc_now():
            user = session.get(WorkspaceUser, login.user_id)
            if user:
                return Workspace(user.id, user.username)
    return None


async def workspace_middleware(request: Request, call_next):
    settings = get_settings()
    if not settings.auth_required or not request.url.path.startswith("/api/v1/"):
        return await call_next(request)

    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin != settings.app_public_url
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "This request must come from the PageIndex workspace"},
        )

    workspace = await run_in_threadpool(
        _authenticated_workspace, request.cookies.get(COOKIE_NAME, "")
    )
    request.state.workspace = workspace
    if (request.method, request.url.path) in PUBLIC_WORKSPACE_ROUTES:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
    if workspace is None:
        return JSONResponse(
            status_code=401, content={"detail": "Sign in to access this workspace"}
        )
    try:
        await run_in_threadpool(_limit_request, workspace.id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    context = current_workspace.set(workspace)
    try:
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        return response
    finally:
        current_workspace.reset(context)


def _limit_request(workspace_id: str) -> None:
    with Session(database.engine) as session:
        increment_quota(
            session,
            f"request:{workspace_id}",
            60,
            limit=get_settings().requests_per_minute,
        )
        session.commit()


def require_auth_mode() -> None:
    if not get_settings().auth_required:
        raise HTTPException(
            status_code=409, detail="Sign-in is disabled for this local workspace"
        )


def valid_password(user: WorkspaceUser | None, password: str) -> bool:
    saved = user.password_hash if user else ""
    salt = saved.partition(":")[0] if saved else "0" * 32
    submitted = hash_password(password, salt)
    return bool(saved) and secrets.compare_digest(submitted, saved)


def auth_rate_limit(
    session: Session,
    request: Request,
    action: str,
    identifier: str = "",
    *,
    limit: int = 3,
) -> None:
    address = request.client.host if request.client else "unknown"
    increment_quota(session, f"auth:{action}:address:{address}", 900, limit=30)
    if identifier:
        increment_quota(
            session, f"auth:{action}:account:{token_hash(identifier)}", 900, limit=limit
        )
    session.commit()


def issue_session(
    session: Session, user: WorkspaceUser, request: Request, response: Response
) -> None:
    token = secrets.token_urlsafe(32)
    session.exec(delete(LoginSession).where(LoginSession.expires_at <= utc_now()))
    if previous_token := request.cookies.get(COOKIE_NAME):
        session.exec(
            delete(LoginSession).where(
                LoginSession.token_hash == token_hash(previous_token)
            )
        )
    session.add(
        LoginSession(
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=utc_now() + SESSION_LIFETIME,
        )
    )
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=get_settings().secure_cookies,
        samesite="strict",
        path="/api/v1",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        path="/api/v1",
        secure=get_settings().secure_cookies,
        httponly=True,
        samesite="strict",
    )


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class WorkspaceStatus(BaseModel):
    auth_required: bool
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    email_verified: bool = False
    has_password: bool = False
    email_enabled: bool = False
    signup_enabled: bool = False
    registration_open: bool = False
    oauth_providers: list[str] = Field(default_factory=list)
    linked_providers: list[str] = Field(default_factory=list)


def workspace_status(
    session: Session, user: WorkspaceUser | None = None
) -> WorkspaceStatus:
    settings = get_settings()
    linked = (
        list(
            session.exec(
                select(OAuthIdentity.provider).where(OAuthIdentity.user_id == user.id)
            ).all()
        )
        if user
        else []
    )
    return WorkspaceStatus(
        auth_required=settings.auth_required,
        username=user.username if user else None,
        first_name=user.first_name if user else None,
        last_name=user.last_name if user else None,
        email=user.email if user else None,
        email_verified=bool(user and user.email_verified),
        has_password=bool(user and user.password_hash),
        email_enabled=settings.auth_required and settings.email_enabled,
        signup_enabled=settings.auth_required
        and settings.auth_allow_signup
        and settings.email_enabled,
        registration_open=settings.auth_required and settings.auth_allow_signup,
        oauth_providers=settings.oauth_providers if settings.auth_required else [],
        linked_providers=linked,
    )


@router.get("/session")
def status(request: Request) -> WorkspaceStatus:
    workspace = getattr(request.state, "workspace", None)
    with Session(database.engine) as session:
        return workspace_status(
            session, session.get(WorkspaceUser, workspace.id) if workspace else None
        )


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> WorkspaceStatus:
    require_auth_mode()
    identifier = body.username.strip().casefold()
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "login", identifier, limit=10)
        credential = (
            (WorkspaceUser.email == identifier) & WorkspaceUser.email_verified.is_(True)
            if "@" in identifier
            else (WorkspaceUser.username == identifier)
        )
        user = session.exec(select(WorkspaceUser).where(credential)).first()
        if not valid_password(user, body.password):
            raise HTTPException(status_code=401, detail="Invalid sign-in credentials")

        saved = user.password_hash
        session.rollback()
        database.lock_auth_transaction(session)
        session.refresh(user)
        if user.password_hash != saved:
            raise HTTPException(status_code=401, detail="Invalid sign-in credentials")
        issue_session(session, user, request, response)
        return workspace_status(session, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with Session(database.engine) as session:
            database.lock_auth_transaction(session)
            session.exec(
                delete(LoginSession).where(LoginSession.token_hash == token_hash(token))
            )
            session.commit()
    clear_session_cookie(response)


class WorkspaceUsage(BaseModel):
    chat_tokens: int
    chat_token_limit: int | None
    provider_requests: int | None
    provider_request_limit: int | None


@router.get("/usage")
def usage(session: SessionDep) -> WorkspaceUsage:
    workspace = current_workspace.get()
    settings = get_settings()
    window = int(utc_now().timestamp()) // 86400 * 86400
    identifier = workspace.id if workspace else "local"
    tokens = session.get(Quota, (f"tokens:{identifier}", window))
    requests = (
        session.get(Quota, (f"provider:{identifier}", window)) if workspace else None
    )
    return WorkspaceUsage(
        chat_tokens=tokens.value if tokens else 0,
        chat_token_limit=settings.chat_tokens_per_day if workspace else None,
        provider_requests=(requests.value if requests else 0) if workspace else None,
        provider_request_limit=settings.provider_requests_per_day
        if workspace
        else None,
    )
