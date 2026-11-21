import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import MagicMock, patch

from database_support import test_engine
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from sqlmodel import Session
from test_api import pdf_bytes

from app import database
from app.config import Settings
from app.document_storage import upload_path
from app.migrate_sqlite import migrate
from app.models import Document, LoginSession, WorkspaceUser, utc_now
from app.preview_cache import preview_cache
from main import app


class TestStorage(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("TEST_DATABASE_URL"), "PostgreSQL test database not provided"
    )
    def test_sqlite_migration_preserves_document_and_pdf(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        source = root / "app.db"
        origin = database.build_engine(URL.create("sqlite", database=str(source)))
        self.addCleanup(origin.dispose)
        database.initialize_database(origin)
        user = WorkspaceUser(username="legacy", password_hash="original")
        doc = Document(
            owner_id=user.id,
            filename="Display name.pdf",
            original_filename="Original.pdf",
            doc_id="provider-id",
        )
        with Session(origin, expire_on_commit=False) as session:
            session.add(user)
            session.flush()
            session.add(doc)
            session.add(
                LoginSession(user_id=user.id, token_hash="old", expires_at=utc_now())
            )
            session.commit()
        folder = root / "uploads"
        folder.mkdir()
        filename = f"{doc.id}_Original.pdf"
        pdf = pdf_bytes(2)
        (folder / filename).write_bytes(pdf)
        target = test_engine(self, "sqlite://")
        destination = root / "migrated"
        before = source.read_bytes()
        stats = migrate(source, target, folder, destination)
        self.assertEqual(stats["document"], 1)
        self.assertEqual(stats["pdf_files"], 1)
        self.assertEqual((destination / filename).read_bytes(), pdf)
        self.assertEqual(source.read_bytes(), before)
        with Session(target) as session:
            saved = session.get(Document, doc.id)
            self.assertEqual(saved.filename, "Display name.pdf")
            self.assertEqual(saved.original_filename, "Original.pdf")
            self.assertEqual(saved.owner_id, user.id)
            self.assertIsNone(session.get(LoginSession, "old"))
        with self.assertRaisesRegex(ValueError, "empty PostgreSQL"):
            migrate(source, target, folder, destination)

    @unittest.skipUnless(
        os.environ.get("TEST_REDIS_URL"), "Redis test server not provided"
    )
    def test_pdf_cache_hits_expires_and_keeps_workspace_access_scoped(self):
        working_dir = Path(self.enterContext(TemporaryDirectory()))
        settings = Settings(
            _env_file=None,
            upload_dir=working_dir,
            redis_url=os.environ["TEST_REDIS_URL"],
            preview_cache_ttl_seconds=2,
        )
        engine = test_engine(self, f"sqlite:///{working_dir}/app.db")
        database.initialize_database(engine)
        self.enterContext(patch.object(database, "engine", engine))
        for module in ("app.document_storage", "app.preview_cache", "app.workspace"):
            self.enterContext(patch(f"{module}.get_settings", return_value=settings))
        cache = preview_cache()
        with Session(engine) as session:
            doc = Document(filename="Original.pdf", doc_id="cache-test", status="ready")
            session.add(doc)
            session.commit()
            path = upload_path(doc)
            path.write_bytes(pdf_bytes(1))
            document_id = doc.id

        provider = MagicMock()
        provider.get_page_content.return_value = [{"text": "Cached source"}]
        self.enterContext(
            patch("app.routers.documents.get_pageindex_client", return_value=provider)
        )
        client = self.enterContext(TestClient(app))
        endpoint = "/api/v1/documents/page-preview?doc_id=cache-test"
        first = client.get(endpoint)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(client.get(first.json()["image_url"]).status_code, 200)
        self.assertEqual(client.get(endpoint).json()["text"], "Cached source")
        provider.get_page_content.assert_called_once()
        self.assertEqual(
            client.patch(
                f"/api/v1/documents/{document_id}", json={"filename": "Renamed"}
            ).status_code,
            200,
        )
        self.assertEqual(client.get(endpoint).json()["filename"], "Renamed.pdf")
        provider.get_page_content.assert_called_once()
        keys = list(cache.client.scan_iter(f"pageindex:pdf:v1:local:{document_id}:*"))
        self.assertEqual(len(keys), 2)
        self.assertTrue(all(0 < cache.client.pttl(key) <= 2000 for key in keys))
        self.assertEqual(
            client.delete(f"/api/v1/documents/{document_id}").status_code, 204
        )
        self.assertEqual(client.get(endpoint).status_code, 404)
        deadline = monotonic() + 3
        while cache.client.exists(*keys) and monotonic() < deadline:
            sleep(0.05)
        self.assertEqual(cache.client.exists(*keys), 0)
