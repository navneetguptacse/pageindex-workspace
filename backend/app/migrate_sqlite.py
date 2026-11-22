import argparse
import shutil
import sqlite3
from contextlib import closing
from filecmp import cmp
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from sqlalchemy.engine import URL, Engine
from sqlmodel import SQLModel, select

from app.config import get_settings
from app.database import build_engine, engine, initialize_database
from app.models import EmailChange, EmailLink, LoginSession, OAuthFlow, WorkItem

TRANSIENT_TABLES = {
    EmailChange.__table__,
    EmailLink.__table__,
    LoginSession.__table__,
    OAuthFlow.__table__,
}


def copy_pdfs(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for pdf in source.iterdir():
        if pdf.suffix.lower() != ".pdf" or not pdf.is_file() or pdf.is_symlink():
            continue
        output = destination / pdf.name
        if output.is_symlink() or (
            output.exists() and not cmp(pdf, output, shallow=False)
        ):
            raise ValueError(f"A different PDF already exists at {output}")
        if not output.exists():
            with NamedTemporaryFile(dir=destination) as temporary:
                shutil.copyfile(pdf, temporary.name)
                output.hardlink_to(temporary.name)
        count += 1
    return count


def migrate(
    source: Path, target: Engine, uploads: Path, destination: Path
) -> dict[str, int]:
    if target.dialect.name != "postgresql":
        raise ValueError("The destination must use PostgreSQL")
    if not source.is_file():
        raise ValueError(f"SQLite database not found at {source}")
    if not uploads.is_dir():
        raise ValueError(f"PDF directory not found at {uploads}")
    with TemporaryDirectory() as directory:
        snapshot = Path(directory) / "snapshot.db"
        with (
            closing(
                sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
            ) as original,
            closing(sqlite3.connect(snapshot)) as copy,
        ):
            original.backup(copy)

        source_engine = build_engine(URL.create("sqlite", database=str(snapshot)))
        try:
            initialize_database(source_engine)
            initialize_database(target)
            tables = [
                table
                for table in SQLModel.metadata.sorted_tables
                if table not in TRANSIENT_TABLES
            ]
            counts = {}
            with source_engine.connect() as origin, target.begin() as writer:
                writer.exec_driver_sql("SELECT pg_advisory_xact_lock(764312800)")
                if any(
                    writer.execute(select(table).limit(1)).first() is not None
                    for table in tables
                ):
                    raise ValueError(
                        "Use an empty PostgreSQL database for the SQLite import"
                    )
                for table in tables:
                    count = 0
                    for batch in (
                        origin.execute(select(table)).mappings().partitions(500)
                    ):
                        rows = [dict(row) for row in batch]
                        if table is WorkItem.__table__:
                            for row in rows:
                                row["lease_until"] = None
                        writer.execute(table.insert(), rows)
                        count += len(rows)
                    counts[table.name] = count
                counts["pdf_files"] = copy_pdfs(uploads, destination)
            return counts
        finally:
            source_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a SQLite backup and PDFs into PostgreSQL"
    )
    parser.add_argument("sqlite_file", type=Path)
    parser.add_argument("--uploads", type=Path)
    args = parser.parse_args()
    uploads = (
        args.uploads
        if args.uploads is not None
        else args.sqlite_file.parent / "uploads"
    )
    try:
        counts = migrate(args.sqlite_file, engine, uploads, get_settings().upload_dir)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    for name, count in counts.items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
