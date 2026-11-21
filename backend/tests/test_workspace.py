import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pypdfium2 as pdfium
from cryptography.fernet import Fernet
from database_support import test_engine
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pageindex.errors import PageIndexAPIError
from sqlmodel import Session, select

from app import database, manage_users
from app.chat_answers import parse_document_list
from app.config import Settings
from app.document_storage import upload_path
from app.models import (
    ChatSession,
    Collection,
    Document,
    ExtractJob,
    Quota,
    WorkItem,
    WorkspaceProviders,
    WorkspaceUser,
    utc_now,
)
from app.pageindex_clients import provider_key
from app.quota import reserve_chat_tokens, settle_chat_tokens
from app.work_queue import process_next
from app.workspace import hash_password
from main import app


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        settings = Settings(
            _env_file=None,
            auth_required=True,
            secure_cookies=False,
            upload_dir=Path(directory) / "uploads",
            provider_credentials_encryption_key=Fernet.generate_key().decode(),
        )
        for name in (
            "app.workspace",
            "app.quota",
            "app.document_storage",
            "app.provider_settings",
            "app.pageindex_clients",
            "main",
        ):
            self.enterContext(patch(f"{name}.get_settings", return_value=settings))
        self.engine = test_engine(self, f"sqlite:///{directory}/app.db")
        self.enterContext(patch.object(database, "engine", self.engine))
        self.enterContext(patch.object(database, "database_url", self.engine.url))
        database.create_db_and_tables()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        with Session(self.engine) as session:
            one = WorkspaceUser(
                username="alice", password_hash=hash_password("alice-password")
            )
            two = WorkspaceUser(
                username="bob", password_hash=hash_password("bob-password")
            )
            session.add_all([one, two])
            session.flush()
            self.alice_id = one.id
            second_document = Document(
                owner_id=two.id,
                doc_id="bob-document",
                filename="private.pdf",
                status="ready",
            )
            session.add_all(
                [
                    Document(
                        owner_id=one.id,
                        doc_id="alice-document",
                        filename="alice.pdf",
                        status="ready",
                    ),
                    second_document,
                    Document(
                        doc_id="local-only", filename="legacy.pdf", status="ready"
                    ),
                ]
            )
            other_chat = ChatSession(owner_id=two.id, title="Private chat")
            session.add(other_chat)
            session.flush()
            self.other_session_id = other_chat.id
            self.other_document_id = second_document.id
            session.commit()

    def login(self):
        response = self.client.post(
            "/api/v1/workspace/login",
            json={"username": "alice", "password": "alice-password"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("HttpOnly", response.headers["set-cookie"])

    def test_isolation_and_logout(self):
        self.assertEqual(self.client.get("/api/v1/documents/").status_code, 401)
        self.login()
        response = self.client.get("/api/v1/documents/")
        self.assertEqual([row["doc_id"] for row in response.json()], ["alice-document"])
        response = self.client.delete(f"/api/v1/documents/{self.other_document_id}")
        self.assertEqual(response.status_code, 404)
        response = self.client.patch(
            f"/api/v1/documents/{self.other_document_id}",
            json={"filename": "renamed.pdf"},
        )
        self.assertEqual(response.status_code, 404)
        with Session(self.engine) as session:
            self.assertEqual(
                session.get(Document, self.other_document_id).filename, "private.pdf"
            )
        self.assertEqual(self.client.get("/api/v1/chat/sessions").json(), [])
        removal = self.client.post(
            "/api/v1/chat/sessions/batch-delete",
            json={"session_ids": [self.other_session_id]},
        )
        self.assertEqual(removal.json(), {"deleted": 0})
        with Session(self.engine) as session:
            self.assertFalse(session.get(ChatSession, self.other_session_id).is_deleted)
        self.assertEqual(self.client.post("/api/v1/workspace/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/v1/documents/").status_code, 401)

    def test_provider_credentials_are_private_and_write_only(self):
        path = "/api/v1/workspace/account/providers"
        self.assertEqual(self.client.get(path).status_code, 401)
        self.login()
        self.assertFalse(self.client.get(path).json()["pageindex_configured"])
        response = self.client.patch(
            path,
            json={"pageindex_api_key": "alice-private-pageindex-key"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["pageindex_configured"])
        self.assertNotIn("alice-private-pageindex-key", response.text)
        with Session(self.engine) as session:
            record = session.get(WorkspaceProviders, self.alice_id)
            self.assertNotEqual(record.pageindex_key, "alice-private-pageindex-key")
        context = database.current_workspace.set(
            database.Workspace(self.alice_id, "alice")
        )
        try:
            self.assertEqual(provider_key(), "alice-private-pageindex-key")
        finally:
            database.current_workspace.reset(context)

        response = self.client.patch(path, json={"pageindex_api_key": None})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["pageindex_configured"])
        response = self.client.patch(
            path, json={"pageindex_api_key": "alice-replacement-key"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.post("/api/v1/workspace/logout")
        self.assertEqual(
            self.client.post(
                "/api/v1/workspace/login",
                json={"username": "bob", "password": "bob-password"},
            ).status_code,
            200,
        )
        self.assertFalse(self.client.get(path).json()["pageindex_configured"])
        duplicate = self.client.patch(
            path, json={"pageindex_api_key": "alice-replacement-key"}
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

    def test_queue_replays_upload_and_persists_provider_progress(self):
        self.login()
        path = "/api/v1/documents/batch"
        headers = {"Prefer": "respond-async", "Idempotency-Key": "upload-123"}
        files = {"files": ("queued.pdf", b"%PDF-1.4 test")}
        first = self.client.post(path, headers=headers, files=files)
        self.assertEqual(first.status_code, 202, first.text)
        resource = first.json()[0]
        self.assertEqual(resource["status"], "queued")
        second = self.client.post(path, headers=headers, files=files)
        self.assertEqual(second.json()[0]["id"], resource["id"])
        conflict = self.client.post(
            path,
            headers=headers,
            files={"files": ("changed.pdf", b"%PDF-1.4 different")},
        )
        self.assertEqual(conflict.status_code, 409)
        renamed = self.client.patch(
            f"/api/v1/documents/{resource['id']}", json={"filename": "Queued report"}
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)

        provider = MagicMock()
        provider.submit_document.return_value = {"doc_id": "queued-remote"}
        provider.get_document.return_value = {"status": "completed"}
        with patch("app.work_queue.get_pageindex_client", return_value=provider):
            self.assertTrue(process_next())
            with patch(
                "app.work_queue.utc_now", return_value=utc_now() + timedelta(seconds=6)
            ):
                self.assertTrue(process_next())
        result = self.client.get(f"/api/v1/documents/{resource['id']}")
        self.assertEqual(result.json()["status"], "ready")
        self.assertEqual(result.json()["doc_id"], "queued-remote")
        self.assertEqual(result.json()["filename"], "Queued report.pdf")
        provider.submit_document.assert_called_once()

    def test_worker_advances_other_pdfs_and_resubmits_rejected_upload(self):
        self.login()
        saved = self.client.patch(
            "/api/v1/workspace/account/providers",
            json={"pageindex_api_key": "workspace-test-key"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        response = self.client.post(
            "/api/v1/documents/batch",
            headers={"Prefer": "respond-async"},
            files=[
                ("files", (filename, b"%PDF-1.4 test"))
                for filename in ("slow.pdf", "fast.pdf", "retry.pdf")
            ],
        )
        self.assertEqual(response.status_code, 202, response.text)
        documents = {row["filename"]: row["id"] for row in response.json()}
        provider = MagicMock()

        def submit(path, **_options):
            filename = Path(path).name.split("_", 1)[1]
            if filename == "retry.pdf":
                raise PageIndexAPIError("Rejected", status_code=401)
            return {"doc_id": filename}

        provider.submit_document.side_effect = submit
        provider.get_document.side_effect = lambda key: {
            "status": "processing" if key == "slow.pdf" else "completed"
        }
        with patch("app.work_queue.get_pageindex_client", return_value=provider):
            for _ in documents:
                self.assertTrue(process_next())
            with patch(
                "app.work_queue.utc_now", return_value=utc_now() + timedelta(seconds=6)
            ):
                self.assertTrue(process_next())
                self.assertTrue(process_next())
            for filename, status in (
                ("slow.pdf", "processing"),
                ("fast.pdf", "ready"),
                ("retry.pdf", "failed"),
            ):
                row = self.client.get(f"/api/v1/documents/{documents[filename]}").json()
                self.assertEqual(row["status"], status)
            provider.submit_document.side_effect = None
            provider.submit_document.return_value = {"doc_id": "retried"}
            retry = self.client.post(
                f"/api/v1/documents/{documents['retry.pdf']}/retry"
            )
            self.assertEqual(retry.status_code, 202, retry.text)
            self.assertEqual(retry.json()["status"], "queued")
            self.assertTrue(process_next())
            provider.get_document_id.assert_not_called()
            self.assertTrue(
                provider.submit_document.call_args.args[0].endswith("_retry.pdf")
            )

    def test_claiming_local_data_moves_pending_upload_and_extract_jobs(self):
        with Session(self.engine) as session:
            source = session.exec(
                select(Document).where(Document.doc_id == "local-only")
            ).one()
            upload = Document(
                doc_id="local-upload", filename="queued.pdf", status="queued"
            )
            extraction = ExtractJob(
                document_id=source.id, pageindex_job_id="", status="queued"
            )
            jobs = [
                WorkItem(kind=kind, fingerprint="pending", resource_ids=[str(row.id)])
                for kind, row in (("upload", upload), ("extract", extraction))
            ]
            ids = [job.id for job in jobs]
            session.add_all([upload, extraction, *jobs])
            session.commit()

        with (
            patch.object(manage_users, "engine", self.engine),
            patch.object(manage_users, "create_db_and_tables"),
            patch("sys.argv", ["manage_users", "new-user", "--claim-local-data"]),
            patch("getpass.getpass", return_value="test-password-only"),
            patch("builtins.print"),
        ):
            manage_users.main()
        with Session(self.engine) as session:
            owner = session.exec(
                select(WorkspaceUser).where(WorkspaceUser.username == "new-user")
            ).one()
            for job_id in ids:
                job = session.get(WorkItem, job_id)
                self.assertEqual(job.owner_id, owner.id)
                self.assertFalse(job.done)
                model = Document if job.kind == "upload" else ExtractJob
                self.assertEqual(
                    session.get(model, UUID(job.resource_ids[0])).owner_id, owner.id
                )

    def test_retry_reuses_stored_pdf_and_upload_job(self):
        self.login()
        upload = self.client.post(
            "/api/v1/documents/batch",
            headers={"Prefer": "respond-async"},
            files={"files": ("report.pdf", b"%PDF-1.4 test")},
        )
        self.assertEqual(upload.status_code, 202, upload.text)
        document_id = UUID(upload.json()[0]["id"])
        endpoint = f"/api/v1/documents/{document_id}/retry"
        with Session(self.engine) as session:
            document = session.get(Document, document_id)
            document.status = "failed"
            document.processing_error = "Provider settings were missing"
            work = session.exec(select(WorkItem)).one()
            work_id = work.id
            work.failures = 4
            other = session.get(Document, self.other_document_id)
            other.status = "failed"
            session.commit()
        self.assertEqual(
            self.client.post(
                f"/api/v1/documents/{self.other_document_id}/retry"
            ).status_code,
            404,
        )

        self.assertEqual(self.client.post(endpoint).status_code, 503)
        saved = self.client.patch(
            "/api/v1/workspace/account/providers",
            json={"pageindex_api_key": "configured-key"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        with Session(self.engine) as session:
            session.get(WorkItem, work_id).lease_until = utc_now() + timedelta(
                minutes=1
            )
            session.commit()
        self.assertEqual(self.client.post(endpoint).status_code, 409)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Document, document_id).status, "failed")
            session.get(WorkItem, work_id).lease_until = None
            session.commit()
        retry = self.client.post(endpoint)
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json()["id"], str(document_id))
        self.assertEqual(retry.json()["status"], "queued")
        self.assertIsNone(retry.json()["processing_error"])
        self.assertEqual(self.client.post(endpoint).status_code, 409)

        with Session(self.engine) as session:
            work = session.exec(select(WorkItem)).one()
            self.assertEqual(work.id, work_id)
            self.assertEqual(work.failures, 0)
        provider = MagicMock()
        provider.submit_document.return_value = {"doc_id": "retried-remote"}
        with patch("pageindex.PageIndexClient", return_value=provider) as client:
            self.assertTrue(process_next())
        client.assert_called_once_with(index={"api_key": "configured-key"})
        provider.submit_document.assert_called_once()
        stored_path = provider.submit_document.call_args.args[0]
        self.assertEqual(Path(stored_path).read_bytes(), b"%PDF-1.4 test")
        result = self.client.get(f"/api/v1/documents/{document_id}").json()
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["doc_id"], "retried-remote")

    def test_document_list_uses_exact_counts_and_respects_scope_without_provider(self):
        self.login()
        with Session(self.engine) as session:
            collection = Collection(
                owner_id=self.alice_id,
                name="Policies",
                pageindex_collection_id="remote",
            )
            session.add(collection)
            session.flush()
            collection_id = str(collection.id)
            document = session.exec(
                select(Document).where(Document.doc_id == "alice-document")
            ).one()
            document.filename = "guide|policies.pdf"
            document.collection_id = collection.id
            document.file_size = 12 * 1024**2
            document.uploaded_at = utc_now() - timedelta(days=1)
            path = upload_path(document)
            path.parent.mkdir(parents=True, exist_ok=True)
            with pdfium.PdfDocument.new() as pdf:
                for _ in range(166):
                    pdf.new_page(100, 100).close()
                pdf.save(path)
            session.add_all(
                [
                    Document(
                        owner_id=self.alice_id,
                        doc_id="missing-file",
                        filename="missing.pdf",
                        status="ready",
                        file_size=1024,
                    ),
                    Document(
                        owner_id=self.alice_id,
                        doc_id="deleted-file",
                        filename="deleted.pdf",
                        status="ready",
                        is_deleted=True,
                    ),
                    Document(
                        owner_id=self.alice_id,
                        doc_id="failed-file",
                        filename="failed.pdf",
                        status="failed",
                    ),
                ]
            )
            session.commit()

        question = (
            "Give me list of document you have to chat. "
            "table format along with no of page document include."
        )
        expected = (
            "| Document | Total pages |\n| --- | ---: |\n| guide\\|policies.pdf | 166 |"
        )
        with (
            patch("app.routers.chat.workspace_chat") as model_provider,
            patch("app.routers.chat.reserve_provider_request") as reserve,
        ):
            for target in (
                {},
                {"collection_id": collection_id},
                {"doc_id": "alice-document"},
            ):
                response = self.client.post(
                    "/api/v1/chat/", json={"question": question, **target}
                )
                self.assertEqual(response.status_code, 201, response.text)
                answer = response.json()
                self.assertEqual(
                    answer["answer"],
                    expected
                    if target
                    else expected + "\n| missing.pdf | Unavailable |",
                )
                self.assertIsNone(answer["model"])
                self.assertIsNone(answer["citations"])
                self.assertIsNone(answer["usage"])
            yesterday = self.client.post(
                "/api/v1/chat/", json={"question": "List documents uploaded yesterday."}
            )
            self.assertEqual(yesterday.status_code, 201, yesterday.text)
            self.assertEqual(
                yesterday.json()["answer"],
                expected + "\n\nUpload dates are based on UTC.",
            )
            large = self.client.post(
                "/api/v1/chat/", json={"question": "List files larger than 10 MB."}
            )
            self.assertEqual(large.status_code, 201, large.text)
            self.assertEqual(large.json()["answer"], expected)
            empty = self.client.post(
                "/api/v1/chat/", json={"question": "List files larger than 20 MB."}
            )
            self.assertEqual(empty.status_code, 201, empty.text)
            self.assertIn("No indexed PDFs match", empty.json()["answer"])
            model_provider.assert_not_called()
            reserve.assert_not_called()
        self.assertIsNone(
            parse_document_list("List files containing the word password.")
        )
        self.assertIsNone(parse_document_list("List documents uploaded last week."))

    def test_chat_history_cursor_reaches_older_conversations_with_tied_times(self):
        self.login()
        updated = utc_now()
        with Session(self.engine) as session:
            session.add_all(
                [
                    ChatSession(
                        id=f"history-{index:03}",
                        owner_id=self.alice_id,
                        updated_at=updated,
                    )
                    for index in range(55)
                ]
            )
            session.commit()
        path = "/api/v1/chat/sessions"
        first = self.client.get(path).json()
        self.assertEqual(len(first), 50)
        cursor = first[-1]
        second = self.client.get(
            path,
            params={
                "before_updated_at": cursor["updated_at"],
                "before_id": cursor["id"],
            },
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(
            [row["id"] for row in second.json()],
            [f"history-{index:03}" for index in range(4, -1, -1)],
        )

    def test_concurrent_chat_token_reservations_share_one_limit(self):
        settings = Settings(_env_file=None, chat_tokens_per_day=100)
        barrier = Barrier(2, timeout=5)

        def reserve():
            barrier.wait()
            with Session(self.engine) as session:
                try:
                    return reserve_chat_tokens(session, self.alice_id, 30, 80)
                except HTTPException as exc:
                    self.assertEqual(exc.status_code, 429)
                    return None

        with patch("app.quota.get_settings", return_value=settings):
            with ThreadPoolExecutor(max_workers=2) as executor:
                reservations = [
                    result
                    for result in executor.map(lambda _: reserve(), range(2))
                    if result
                ]
            self.assertEqual(len(reservations), 1)
            reservation = reservations[0]
            self.assertEqual(reservation.output_tokens, 70)
            with Session(self.engine) as session:
                settle_chat_tokens(session, reservation, 60)
                next_reservation = reserve_chat_tokens(session, self.alice_id, 30, 80)
                self.assertEqual(next_reservation.output_tokens, 10)
                settle_chat_tokens(session, next_reservation, 33)
                key = (reservation.key, reservation.timestamp // 86400 * 86400)
                self.assertEqual(session.get(Quota, key).value, 93)

    def test_workspace_chat_retrieves_only_owned_documents_and_tracks_tokens(self):
        self.login()
        path = "/api/v1/workspace/account/providers"
        chat = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "my-chat-key",
        }
        saved = self.client.patch(path, json={"chat": chat})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn(chat["api_key"], saved.text)
        saved = self.client.patch(
            path, json={"chat": {"provider": "deepseek", "model": "deepseek-reasoner"}}
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        rejected = self.client.patch(
            path, json={"chat": {"provider": "openai", "model": "gpt-4o"}}
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        search = MagicMock()
        search.search.return_value = {
            "results": [
                {
                    "documents": [
                        {
                            "id": "alice-document",
                            "pages": [
                                {"page": 2, "relevance": 0.9, "text": "Known fact."}
                            ],
                        },
                        {
                            "id": "bob-document",
                            "pages": [
                                {
                                    "page": 3,
                                    "relevance": 1,
                                    "text": "Other account data.",
                                }
                            ],
                        },
                    ]
                }
            ]
        }
        usage = MagicMock()
        usage.model_dump.return_value = {"total_tokens": 42}
        completion = MagicMock(
            side_effect=[
                SimpleNamespace(
                    usage=usage,
                    choices=[
                        SimpleNamespace(
                            finish_reason="length",
                            message=SimpleNamespace(content=None),
                        )
                    ],
                ),
                SimpleNamespace(
                    usage=usage,
                    choices=[
                        SimpleNamespace(
                            finish_reason="stop",
                            message=SimpleNamespace(
                                content="The known fact is cited [source 1]."
                            ),
                        )
                    ],
                ),
            ]
        )
        with (
            patch("app.chat_answers.get_search_client", return_value=search),
            patch.dict(
                sys.modules, {"litellm": SimpleNamespace(completion=completion)}
            ),
        ):
            response = self.client.post(
                "/api/v1/chat/", json={"question": "State the fact"}
            )
        self.assertEqual(response.status_code, 201, response.text)
        search.search.assert_called_once()
        self.assertEqual(search.search.call_args.kwargs["document"], "alice-document")
        self.assertEqual(completion.call_count, 2)
        first, retry = completion.call_args_list
        self.assertEqual(first.kwargs["model"], "deepseek/deepseek-reasoner")
        self.assertEqual(first.kwargs["api_key"], chat["api_key"])
        self.assertEqual(first.kwargs["messages"][-1], retry.kwargs["messages"][-1])
        self.assertGreater(retry.kwargs["max_tokens"], first.kwargs["max_tokens"])
        self.assertEqual(
            response.json()["answer"], "The known fact is cited [source 1]."
        )
        self.assertNotIn("Other account data", str(completion.call_args))
        self.assertEqual(response.json()["citations"][0]["doc_id"], "alice-document")
        self.assertEqual(
            self.client.get("/api/v1/workspace/usage").json()["chat_tokens"], 84
        )

    def test_provider_quota_blocks_new_jobs_but_allows_idempotent_replay(self):
        self.login()
        settings = Settings(
            _env_file=None, auth_required=True, provider_requests_per_day=1
        )
        path = "/api/v1/documents/batch"
        files = {"files": ("queued.pdf", b"%PDF-1.4 quota")}
        with patch("app.quota.get_settings", return_value=settings):
            for key, expected in (
                ("first-123", 202),
                ("first-123", 202),
                ("other-123", 429),
            ):
                response = self.client.post(
                    path,
                    headers={"Prefer": "respond-async", "Idempotency-Key": key},
                    files=files,
                )
                self.assertEqual(response.status_code, expected, response.text)


if __name__ == "__main__":
    unittest.main()
