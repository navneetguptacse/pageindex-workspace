from collections.abc import Generator
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import with_loader_criteria
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.config import get_settings
from app.models import (
    ChatHistory,
    ChatSession,
    Collection,
    Document,
    ExtractJob,
    WorkspaceRecord,
    WorkspaceUser,
)


@dataclass(frozen=True)
class Workspace:
    id: str
    username: str


current_workspace: ContextVar[Workspace | None] = ContextVar(
    "current_workspace", default=None
)


class WorkspaceSession(Session):
    pass


@event.listens_for(WorkspaceSession, "do_orm_execute")
def _scope_workspace_queries(state) -> None:
    if state.is_select or state.is_update or state.is_delete:
        owner_id = state.session.info["owner_id"]
        state.statement = state.statement.options(
            *[
                with_loader_criteria(
                    model, model.owner_id == owner_id, include_aliases=True
                )
                for model in (
                    Collection,
                    Document,
                    ChatSession,
                    ChatHistory,
                    ExtractJob,
                )
            ]
        )


@event.listens_for(WorkspaceSession, "before_flush")
def _assign_workspace(session, _context, _instances) -> None:
    for row in session.new:
        if isinstance(row, WorkspaceRecord):
            row.owner_id = session.info["owner_id"]


def build_engine(url: URL) -> Engine:
    sqlite = url.get_backend_name() == "sqlite"
    if sqlite:
        options = (
            {"poolclass": StaticPool} if url.database in (None, "", ":memory:") else {}
        )
        result = create_engine(
            url, connect_args={"check_same_thread": False}, **options
        )
        event.listen(result, "connect", _configure_sqlite)
        return result
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def _configure_sqlite(connection, _) -> None:
    connection.execute("PRAGMA foreign_keys=ON")


settings = get_settings()
database_url = (
    URL.create(
        "postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        database=settings.postgres_db,
    )
    if settings.postgres_host
    else make_url(settings.database_url)
)
engine = build_engine(database_url)


def lock_auth_transaction(session: Session) -> None:
    connection = session.connection()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(764312801)")


WORKSPACE_NAME_COLUMNS = ("first_name", "last_name")


LEGACY_SQLITE_COLUMNS = {
    Document.__tablename__: (
        ("original_filename", "VARCHAR"),
        ("processing_error", "VARCHAR"),
        ("is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
        ("deleted_at", "DATETIME"),
    ),
    ChatSession.__tablename__: (
        ("is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
        ("deleted_at", "DATETIME"),
    ),
    ExtractJob.__tablename__: (
        ("processing_error", "VARCHAR"),
        ("background", "BOOLEAN NOT NULL DEFAULT 0"),
        ("is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
        ("deleted_at", "DATETIME"),
        ("usage", "JSON"),
        ("extract_metadata", "JSON"),
    ),
    ChatHistory.__tablename__: (("session_id", "VARCHAR"), ("usage", "JSON")),
    Collection.__tablename__: (),
    WorkspaceUser.__tablename__: (
        ("email", "VARCHAR"),
        ("email_verified", "BOOLEAN NOT NULL DEFAULT 0"),
        *((name, "VARCHAR") for name in WORKSPACE_NAME_COLUMNS),
    ),
}


def initialize_database(target: Engine) -> None:
    with target.begin() as connection:
        if target.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(764312800)")
            SQLModel.metadata.create_all(connection)
            for name in WORKSPACE_NAME_COLUMNS:
                connection.exec_driver_sql(
                    f"ALTER TABLE {WorkspaceUser.__tablename__} ADD COLUMN IF NOT EXISTS {name} VARCHAR"
                )
            return
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        SQLModel.metadata.create_all(connection)
        for table, columns in LEGACY_SQLITE_COLUMNS.items():
            existing = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            owner_column = (
                ()
                if table == WorkspaceUser.__tablename__
                else (("owner_id", "VARCHAR REFERENCES workspaceuser(id)"),)
            )
            for name, definition in (*columns, *owner_column):
                if name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    )
        for table in SQLModel.metadata.tables.values():
            for index in table.indexes:
                index.create(connection, checkfirst=True)


def create_db_and_tables() -> None:
    if engine.dialect.name == "sqlite" and database_url.database not in (
        None,
        "",
        ":memory:",
    ):
        Path(database_url.database).parent.mkdir(parents=True, exist_ok=True)
    initialize_database(engine)


def get_session() -> Generator[Session, None, None]:
    workspace = current_workspace.get()
    with WorkspaceSession(
        engine, info={"owner_id": workspace.id if workspace else None}
    ) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
