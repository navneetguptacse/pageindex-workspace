import argparse
import getpass
import re

from sqlalchemy import update
from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import (
    ChatHistory,
    ChatSession,
    Collection,
    Document,
    ExtractJob,
    WorkspaceUser,
)
from app.workspace import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a workspace account")
    parser.add_argument("username")
    parser.add_argument(
        "--claim-local-data",
        action="store_true",
        help="Assign unowned local data to this account",
    )
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,63}", username):
        parser.error("Use 3–64 letters, digits, periods, underscores, or hyphens")
    password = getpass.getpass("New password: ")
    if not 12 <= len(password) <= 256:
        parser.error("Use a password between 12 and 256 characters")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords differ")

    create_db_and_tables()
    with Session(engine) as session:
        if session.exec(
            select(WorkspaceUser.id).where(WorkspaceUser.username == username)
        ).first():
            parser.error("That username already exists")
        user = WorkspaceUser(username=username, password_hash=hash_password(password))
        session.add(user)
        session.flush()
        if args.claim_local_data:
            for model in (Collection, Document, ChatSession, ChatHistory, ExtractJob):
                session.exec(
                    update(model)
                    .where(model.owner_id.is_(None))
                    .values(owner_id=user.id)
                )
        session.commit()
    print(f"Created workspace account {username}")


if __name__ == "__main__":
    main()
