from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from app.config import get_settings
from app.database import current_workspace
from app.models import Quota


def increment_quota(
    session: Session, key: str, interval: int, amount: int = 1, limit: int | None = None
) -> None:
    now = int(datetime.now(UTC).timestamp())
    window = now // interval * interval
    insert = (
        postgres_insert
        if session.get_bind().dialect.name == "postgresql"
        else sqlite_insert
    )
    statement = insert(Quota).values(key=key, window=window, value=amount)
    statement = statement.on_conflict_do_update(
        index_elements=[Quota.key, Quota.window],
        set_={"value": Quota.value + amount},
        where=(Quota.value + amount <= limit) if limit is not None else None,
    )
    value = session.exec(statement.returning(Quota.value)).scalar_one_or_none()
    if value is None:
        raise HTTPException(
            status_code=429,
            detail="Workspace usage limit reached",
            headers={"Retry-After": str(window + interval - now)},
        )


def reserve_provider_request(
    session: Session, *, chat: bool = False, amount: int = 1, commit: bool = True
) -> None:
    workspace = current_workspace.get()
    if workspace is None:
        return
    settings = get_settings()
    if chat:
        window = int(datetime.now(UTC).timestamp()) // 86400 * 86400
        used = session.get(Quota, (f"tokens:{workspace.id}", window))
        if used and used.value >= settings.chat_tokens_per_day:
            raise HTTPException(
                status_code=429, detail="Workspace daily chat token limit reached"
            )
    if amount > settings.provider_requests_per_day:
        raise HTTPException(
            status_code=429, detail="Workspace daily provider request limit reached"
        )
    increment_quota(
        session,
        f"provider:{workspace.id}",
        86400,
        amount,
        settings.provider_requests_per_day,
    )
    if commit:
        session.commit()


def record_chat_tokens(session: Session, amount: int) -> None:
    workspace = current_workspace.get()
    if amount > 0:
        identifier = workspace.id if workspace else "local"
        increment_quota(session, f"tokens:{identifier}", 86400, amount)
        session.commit()
