import logging
from datetime import timedelta
from secrets import compare_digest, randbelow, token_urlsafe
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, delete, select

from app import database
from app.account_email import AccountEmail, EmailDeliveryError, send_email
from app.config import Settings, get_settings
from app.models import EmailChange, EmailLink, LoginSession, WorkspaceUser, utc_now
from app.workspace import (
    COOKIE_NAME,
    WORKSPACE_API,
    WorkspaceStatus,
    auth_rate_limit,
    clear_session_cookie,
    hash_password,
    issue_session,
    require_auth_mode,
    token_hash,
    valid_password,
    workspace_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix=WORKSPACE_API, tags=["workspace"])
EMAIL_LINK_LIFETIME = timedelta(minutes=30)
EMAIL_CODE_LIFETIME = timedelta(minutes=10)
PersonName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]


class EmailRequest(BaseModel):
    email: EmailStr


class SetPasswordRequest(BaseModel):
    token: str = Field(min_length=43, max_length=43)
    password: str = Field(min_length=12, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class ProfileNames(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: PersonName
    last_name: PersonName


class EmailChangeRequest(EmailRequest):
    password: str | None = Field(default=None, min_length=1, max_length=256)


class EmailChangeConfirmation(EmailRequest):
    code: str = Field(pattern=r"^[0-9]{6}$")


class SignupConfirmation(SetPasswordRequest):
    first_name: PersonName | None = None
    last_name: PersonName | None = None
    username: str = Field(
        min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.-]+$"
    )


class EmailVerification(BaseModel):
    token: str = Field(min_length=43, max_length=43)


class LinkEmailRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=256)


def _email_settings() -> Settings:
    require_auth_mode()
    settings = get_settings()
    if not settings.email_enabled:
        raise HTTPException(status_code=503, detail="Account email is unavailable")
    return settings


def _deliver(settings: Settings, recipient: str, message: AccountEmail) -> None:
    try:
        send_email(settings, recipient, message)
    except EmailDeliveryError:
        logger.warning("Account email delivery failed for template %s", message.subject)


def _queue_link(
    session: Session,
    background: BackgroundTasks,
    settings: Settings,
    purpose: str,
    email: str,
    subject: str,
    action: str,
    user_id: str | None = None,
) -> None:
    token = token_urlsafe(32)
    session.exec(delete(EmailLink).where(EmailLink.expires_at <= utc_now()))
    session.add(
        EmailLink(
            token_hash=token_hash(token),
            purpose=purpose,
            email=email,
            user_id=user_id,
            expires_at=utc_now() + EMAIL_LINK_LIFETIME,
        )
    )
    session.commit()
    fragment = urlencode({"auth": purpose, "token": token})
    route = "complete-registration" if purpose == "signup" else purpose
    link = f"{settings.app_public_url}/{route}#{fragment}"
    message = AccountEmail(
        subject,
        f"{action} on PageIndex:\n\n{link}\n\nThis link expires in 30 minutes. If you did not request it, you can ignore this email.",
    )
    background.add_task(_deliver, settings, email, message)


def _take_link(session: Session, purpose: str, token: str) -> EmailLink:
    result = session.exec(
        delete(EmailLink)
        .where(
            EmailLink.token_hash == token_hash(token),
            EmailLink.purpose == purpose,
            EmailLink.expires_at > utc_now(),
        )
        .returning(EmailLink)
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(
            status_code=400, detail="This link is invalid, expired, or already used"
        )
    return result


def _user_by_email(session: Session, email: str) -> WorkspaceUser | None:
    return session.exec(
        select(WorkspaceUser).where(WorkspaceUser.email == email)
    ).one_or_none()


@router.post("/signup", status_code=202)
def signup(
    body: EmailRequest, request: Request, background: BackgroundTasks
) -> dict[str, str]:
    settings = _email_settings()
    if not settings.auth_allow_signup:
        raise HTTPException(status_code=403, detail="Account registration is disabled")
    email = body.email.casefold()
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "signup", email)
        if _user_by_email(session, email) is None:
            _queue_link(
                session,
                background,
                settings,
                "signup",
                email,
                "Verify your PageIndex email",
                "Verify your email and create your account",
            )
    return {
        "message": "If this address can be registered, you’ll receive a verification link."
    }


@router.post("/verify-signup", status_code=201)
def verify_signup(
    body: SignupConfirmation, request: Request, response: Response
) -> WorkspaceStatus:
    require_auth_mode()
    if not get_settings().auth_allow_signup:
        raise HTTPException(status_code=403, detail="Account registration is disabled")
    with Session(database.engine) as session:
        link = _take_link(session, "signup", body.token)
        if _user_by_email(session, link.email) is not None:
            raise HTTPException(
                status_code=409,
                detail="Sign in to the account associated with this email",
            )
        if (
            session.exec(
                select(WorkspaceUser.id).where(WorkspaceUser.username == body.username)
            ).first()
            is not None
        ):
            raise HTTPException(
                status_code=409, detail="That username is already in use"
            )
        user = WorkspaceUser(
            username=body.username,
            first_name=body.first_name,
            last_name=body.last_name,
            email=link.email,
            email_verified=True,
            password_hash=hash_password(body.password),
        )
        session.add(user)
        try:
            session.flush()
            issue_session(session, user, request, response)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="This email or username is already in use"
            ) from exc
        return workspace_status(session, user)


def _account_workspace(request: Request) -> database.Workspace:
    require_auth_mode()
    workspace = request.state.workspace
    if workspace is None:
        raise HTTPException(401, "Sign in to manage your account.")
    return workspace


def _active_account(
    session: Session, session_hash: str, workspace: database.Workspace
) -> WorkspaceUser:
    login = session.get(LoginSession, session_hash)
    if login and login.user_id == workspace.id and login.expires_at > utc_now():
        user = session.get(WorkspaceUser, workspace.id)
        if user is not None:
            return user
    raise HTTPException(401, "Sign in to manage your account.")


@router.patch("/account/profile")
def update_profile(body: ProfileNames, request: Request) -> WorkspaceStatus:
    workspace = _account_workspace(request)
    with Session(database.engine) as session:
        database.lock_auth_transaction(session)
        user = _active_account(
            session, token_hash(request.cookies.get(COOKIE_NAME, "")), workspace
        )
        user.first_name = body.first_name
        user.last_name = body.last_name
        session.commit()
        return workspace_status(session, user)


@router.post("/account/email/change", status_code=202)
def request_email_change(body: EmailChangeRequest, request: Request) -> dict[str, str]:
    settings = _email_settings()
    workspace = _account_workspace(request)
    cookie = request.cookies.get(COOKIE_NAME, "")
    session_hash = token_hash(cookie)
    email = body.email.casefold()
    code = f"{randbelow(1_000_000):06d}"
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "email-change", workspace.id)
        database.lock_auth_transaction(session)
        user = _active_account(session, session_hash, workspace)
        if user.password_hash and not valid_password(user, body.password or ""):
            raise HTTPException(403, "Enter your current password.")
        if email == user.email and user.email_verified:
            raise HTTPException(409, "This is already your verified email.")
        existing = _user_by_email(session, email)
        if existing and existing.id != user.id:
            raise HTTPException(409, "Choose a different email address.")
        session.exec(delete(EmailChange).where(EmailChange.expires_at <= utc_now()))
        change = session.get(EmailChange, workspace.id) or EmailChange(
            user_id=workspace.id
        )
        change.email = email
        change.session_hash = session_hash
        change.code_hash = token_hash(f"{cookie}:{code}")
        change.expires_at = utc_now() + EMAIL_CODE_LIFETIME
        session.add(change)
        session.commit()

    try:
        send_email(
            settings,
            email,
            AccountEmail(
                "Verify your new PageIndex email",
                f"Your PageIndex verification code is {code}.\n\nIt expires in 10 minutes.",
            ),
        )
    except EmailDeliveryError:
        logger.warning("Could not deliver an email change verification code")
        raise HTTPException(
            503, "Could not send the verification code. Try again."
        ) from None
    return {"message": "Verification code sent. Check your new email."}


@router.post("/account/email/confirm")
def confirm_email_change(
    body: EmailChangeConfirmation, request: Request, background: BackgroundTasks
) -> WorkspaceStatus:
    workspace = _account_workspace(request)
    cookie = request.cookies.get(COOKIE_NAME, "")
    session_hash = token_hash(cookie)
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "email-code", workspace.id, limit=5)
        database.lock_auth_transaction(session)
        user = _active_account(session, session_hash, workspace)
        change = session.get(EmailChange, workspace.id)
        if (
            change is None
            or change.session_hash != session_hash
            or change.email != body.email.casefold()
            or change.expires_at <= utc_now()
            or not compare_digest(change.code_hash, token_hash(f"{cookie}:{body.code}"))
        ):
            raise HTTPException(
                400, "The code is invalid or expired. Request a new code if needed."
            )
        existing = _user_by_email(session, change.email)
        if existing and existing.id != user.id:
            raise HTTPException(409, "Choose a different email address.")
        previous_email = user.email if user.email_verified else None
        user.email = change.email
        user.email_verified = True
        session.delete(change)
        session.exec(
            delete(EmailLink).where(
                EmailLink.user_id == user.id,
                EmailLink.purpose.in_(("verify-email", "reset-password")),
            )
        )
        try:
            session.commit()
        except IntegrityError as exc:
            raise HTTPException(409, "Choose a different email address.") from exc
        result = workspace_status(session, user)

    settings = get_settings()
    if previous_email and previous_email != result.email and settings.email_enabled:
        background.add_task(
            _deliver,
            settings,
            previous_email,
            AccountEmail(
                "Your PageIndex email changed",
                "The verified email on your PageIndex account was changed.",
            ),
        )
    return result


@router.post("/account/email", status_code=202)
def add_email(
    body: LinkEmailRequest, request: Request, background: BackgroundTasks
) -> dict[str, str]:
    settings = _email_settings()
    workspace = getattr(request.state, "workspace", None)
    if workspace is None:
        raise HTTPException(status_code=401, detail="Sign in to verify your email")
    email = body.email.casefold()
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "add-email", workspace.id)
        user = session.get(WorkspaceUser, workspace.id)
        if not valid_password(user, body.password):
            raise HTTPException(status_code=403, detail="Enter your current password")
        if user.email_verified:
            raise HTTPException(
                status_code=409, detail="Your account already has a verified email"
            )
        if _user_by_email(session, email) is None:
            _queue_link(
                session,
                background,
                settings,
                "verify-email",
                email,
                "Verify your PageIndex email",
                "Verify your recovery email",
                user.id,
            )
    return {
        "message": "If this address is available, you’ll receive a verification link."
    }


@router.post("/verify-email")
def verify_email(body: EmailVerification) -> dict[str, str]:
    require_auth_mode()
    with Session(database.engine) as session:
        database.lock_auth_transaction(session)
        link = _take_link(session, "verify-email", body.token)
        user = session.get(WorkspaceUser, link.user_id)
        if user is None or user.email_verified or _user_by_email(session, link.email):
            raise HTTPException(
                status_code=409, detail="This email can no longer be verified"
            )
        user.email = link.email
        user.email_verified = True
        try:
            session.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="This email can no longer be verified"
            ) from exc
    return {
        "message": "Email verified. You can now use it to sign in or reset your password."
    }


@router.post("/forgot-password", status_code=202)
def forgot_password(
    body: EmailRequest, request: Request, background: BackgroundTasks
) -> dict[str, str]:
    settings = _email_settings()
    email = body.email.casefold()
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "forgot-password", email)
        user = _user_by_email(session, email)
        if user and user.email_verified and user.password_hash:
            _queue_link(
                session,
                background,
                settings,
                "reset-password",
                email,
                "Reset your PageIndex password",
                "Choose a new password",
                user.id,
            )
    return {
        "message": "If a password account uses this address, you’ll receive a reset link."
    }


def _revoke_sessions(session: Session, user_id: str) -> None:
    session.exec(delete(LoginSession).where(LoginSession.user_id == user_id))


def _replace_password(session: Session, user: WorkspaceUser, password: str) -> None:
    user.password_hash = hash_password(password)
    _revoke_sessions(session, user.id)
    session.exec(delete(EmailChange).where(EmailChange.user_id == user.id))
    session.exec(
        delete(EmailLink).where(
            EmailLink.user_id == user.id, EmailLink.purpose == "reset-password"
        )
    )
    session.commit()


def _notify_password_change(
    background: BackgroundTasks, settings: Settings, email: str | None
) -> None:
    if settings.email_enabled and email:
        background.add_task(
            _deliver,
            settings,
            email,
            AccountEmail(
                "Your PageIndex password changed",
                "Your PageIndex password was changed and existing sessions were signed out. If you did not make this change, use password reset to secure your account.",
            ),
        )


@router.post("/account/password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
) -> dict[str, str]:
    require_auth_mode()
    workspace = request.state.workspace
    if workspace is None:
        raise HTTPException(status_code=401, detail="Sign in to change your password")
    with Session(database.engine) as session:
        auth_rate_limit(session, request, "change-password", workspace.id, limit=5)
        database.lock_auth_transaction(session)
        login = session.get(
            LoginSession, token_hash(request.cookies.get(COOKIE_NAME, ""))
        )
        if login is None or login.expires_at <= utc_now():
            raise HTTPException(
                status_code=401, detail="Sign in to change your password"
            )
        user = session.get(WorkspaceUser, workspace.id)
        if not valid_password(user, body.current_password):
            raise HTTPException(status_code=403, detail="Enter your current password")
        email = user.email if user.email_verified else None
        _replace_password(session, user, body.new_password)
    clear_session_cookie(response)
    _notify_password_change(background, get_settings(), email)
    return {"message": "Password updated. Sign in with your new password."}


@router.post("/account/logout-all", status_code=204)
def logout_everywhere(request: Request, response: Response) -> None:
    require_auth_mode()
    workspace = request.state.workspace
    if workspace is None:
        raise HTTPException(status_code=401, detail="Sign in to manage your sessions")
    with Session(database.engine) as session:
        database.lock_auth_transaction(session)
        _revoke_sessions(session, workspace.id)
        session.commit()
    clear_session_cookie(response)


@router.post("/reset-password")
def reset_password(
    body: SetPasswordRequest, response: Response, background: BackgroundTasks
) -> dict[str, str]:
    require_auth_mode()
    settings = get_settings()
    with Session(database.engine) as session:
        database.lock_auth_transaction(session)
        link = _take_link(session, "reset-password", body.token)
        user = session.get(WorkspaceUser, link.user_id)
        if (
            not user
            or not user.email_verified
            or user.email != link.email
            or not user.password_hash
        ):
            raise HTTPException(status_code=400, detail="This reset link is invalid")
        _replace_password(session, user, body.password)
    clear_session_cookie(response)
    _notify_password_change(background, settings, link.email)
    return {"message": "Password updated. Sign in with your new password."}
