from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from app.config import get_settings
from app.database import current_workspace
from app.models import Quota


def increment_quota(
    session: Session,
    key: str,
    interval: int,
    amount: int = 1,
    limit: int | None = None,
    *,
    timestamp: int | None = None,
) -> int:
    now = int(datetime.now(UTC).timestamp()) if timestamp is None else timestamp
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
    return value


def reserve_provider_request(
    session: Session, *, amount: int = 1, commit: bool = True
) -> None:
    workspace = current_workspace.get()
    if workspace is None:
        return
    settings = get_settings()
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


@dataclass(frozen=True)
class ChatTokenReservation:
    key: str
    timestamp: int
    amount: int
    output_tokens: int


def reserve_chat_tokens(
    session: Session, workspace_id: str, input_bound: int, requested_output: int
) -> ChatTokenReservation:
    key = f"tokens:{workspace_id}"
    timestamp = int(datetime.now(UTC).timestamp())
    used = increment_quota(session, key, 86400, amount=0, timestamp=timestamp)
    output = min(
        requested_output, get_settings().chat_tokens_per_day - used - input_bound
    )
    if output <= 0:
        session.rollback()
        raise HTTPException(
            status_code=429,
            detail="Not enough daily chat tokens for this request. Try a shorter conversation or wait for the daily reset.",
            headers={"Retry-After": str(86400 - timestamp % 86400)},
        )
    amount = input_bound + output
    increment_quota(session, key, 86400, amount=amount, timestamp=timestamp)
    session.commit()
    return ChatTokenReservation(key, timestamp, amount, output)


def settle_chat_tokens(
    session: Session, reservation: ChatTokenReservation, actual: int
) -> None:
    increment_quota(
        session,
        reservation.key,
        86400,
        amount=actual - reservation.amount,
        timestamp=reservation.timestamp,
    )
    session.commit()


def record_chat_tokens(session: Session, amount: int) -> None:
    workspace = current_workspace.get()
    if amount > 0:
        identifier = workspace.id if workspace else "local"
        increment_quota(session, f"tokens:{identifier}", 86400, amount)
        session.commit()
