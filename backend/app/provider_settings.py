import hmac
from dataclasses import dataclass
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlmodel import Session, select

from app import database
from app.config import Settings, get_settings
from app.database import SessionDep, Workspace, current_workspace
from app.models import WorkspaceProviders
from app.workspace import WORKSPACE_API

ChatProvider = Literal["openai", "deepseek", "anthropic", "gemini"]
router = APIRouter(prefix=f"{WORKSPACE_API}/account", tags=["workspace"])


class ProviderSetupError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=503, detail=detail)


class ChatProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ChatProvider
    model: str = Field(
        min_length=1, max_length=150, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
    api_key: SecretStr | None = None


class ProviderSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pageindex_api_key: SecretStr | None = None
    chat: ChatProviderUpdate | None = None


class ProviderSettingsRead(BaseModel):
    pageindex_configured: bool
    chat_configured: bool
    chat_provider: ChatProvider | None
    chat_model: str | None


@dataclass(frozen=True)
class WorkspaceChat:
    model: str
    api_key: SecretStr


def _cipher(settings: Settings) -> Fernet:
    try:
        return Fernet(settings.provider_credentials_encryption_key.get_secret_value())
    except (ValueError, TypeError) as exc:
        raise ProviderSetupError(
            "Provider credential storage is unavailable. Contact the workspace administrator."
        ) from exc


def _key_bytes(value: SecretStr) -> bytes:
    key = value.get_secret_value().strip()
    if not key or len(key) > 4096 or any(not 33 <= ord(char) <= 126 for char in key):
        raise HTTPException(422, "Enter a valid API key.")
    return key.encode()


def _save_pageindex_key(
    session: Session,
    record: WorkspaceProviders,
    value: SecretStr | None,
    settings: Settings,
) -> None:
    if value is None:
        record.pageindex_key = record.pageindex_key_digest = None
        return
    key = _key_bytes(value)
    cipher = _cipher(settings)
    digest = hmac.digest(
        settings.provider_credentials_encryption_key.get_secret_value().encode(),
        b"pageindex-key:" + key,
        "sha256",
    ).hex()
    duplicate = session.exec(
        select(WorkspaceProviders.user_id).where(
            WorkspaceProviders.pageindex_key_digest == digest,
            WorkspaceProviders.user_id != record.user_id,
        )
    ).first()
    if duplicate:
        raise HTTPException(409, "Use a separate PageIndex API key for this account.")
    record.pageindex_key = cipher.encrypt(key).decode()
    record.pageindex_key_digest = digest


def _decrypt(value: str, settings: Settings) -> str:
    try:
        return _cipher(settings).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ProviderSetupError(
            "Saved provider credentials could not be read. Contact the workspace administrator."
        ) from exc


def _signed_in() -> Workspace:
    workspace = current_workspace.get()
    if workspace is None:
        raise HTTPException(401, "Sign in to manage provider settings.")
    return workspace


def workspace_pageindex_key(workspace: Workspace, settings: Settings) -> str:
    with Session(database.engine) as session:
        record = session.get(WorkspaceProviders, workspace.id)
        key = record.pageindex_key if record else None
    if key:
        return _decrypt(key, settings)
    raise ProviderSetupError(
        "Add a PageIndex API key in Account settings → Provider settings."
    )


def workspace_chat(session: Session, workspace: Workspace) -> WorkspaceChat:
    record = session.get(WorkspaceProviders, workspace.id)
    if record and record.chat_key and record.chat_provider and record.chat_model:
        return WorkspaceChat(
            f"{record.chat_provider}/{record.chat_model}",
            SecretStr(_decrypt(record.chat_key, get_settings())),
        )
    raise ProviderSetupError(
        "Set your chat provider, API key, and model in Account settings → Provider settings."
    )


def _read_settings(record: WorkspaceProviders | None) -> ProviderSettingsRead:
    return ProviderSettingsRead(
        pageindex_configured=bool(record and record.pageindex_key),
        chat_configured=bool(record and record.chat_key),
        chat_provider=record.chat_provider if record else None,
        chat_model=record.chat_model if record else None,
    )


@router.get("/providers")
def get_providers(session: SessionDep) -> ProviderSettingsRead:
    workspace = _signed_in()
    return _read_settings(session.get(WorkspaceProviders, workspace.id))


@router.patch("/providers")
def update_providers(
    body: ProviderSettingsUpdate, session: SessionDep
) -> ProviderSettingsRead:
    workspace = _signed_in()
    settings = get_settings()
    database.lock_auth_transaction(session)
    record = session.get(WorkspaceProviders, workspace.id) or WorkspaceProviders(
        user_id=workspace.id
    )
    if "pageindex_api_key" in body.model_fields_set:
        _save_pageindex_key(session, record, body.pageindex_api_key, settings)
    if "chat" in body.model_fields_set:
        chat = body.chat
        if chat is None:
            record.chat_provider = record.chat_model = record.chat_key = None
        else:
            if chat.api_key is not None:
                record.chat_key = (
                    _cipher(settings).encrypt(_key_bytes(chat.api_key)).decode()
                )
            elif record.chat_provider != chat.provider or not record.chat_key:
                raise HTTPException(
                    422, "Enter an API key for the selected chat provider."
                )
            record.chat_provider = chat.provider
            record.chat_model = chat.model
    session.add(record)
    result = _read_settings(record)
    session.commit()
    return result
