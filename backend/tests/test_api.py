import io
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pypdfium2 as pdfium
from database_support import test_engine
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.config import Settings
from app.database import get_session
from app.models import ChatHistory, ChatSession, Document
from main import app


def chat_result(answer, finish_reason="stop"):
    return {
        "choices": [{"message": {"content": answer}, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
            "prompt_tokens_details": {"cached_tokens": 5},
        },
    }


def pdf_bytes(page_count):
    output = io.BytesIO()
    with pdfium.PdfDocument.new() as pdf:
        for _ in range(page_count):
            pdf.new_page(100, 100).close()
        pdf.save(output)
    return output.getvalue()


class TestPageIndexAPI(unittest.TestCase):
    def setUp(self):
        temporary_directory = TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.settings = Settings(
            _env_file=None, auth_required=False, upload_dir=temporary_directory.name
        )
        self.enterContext(
            patch("app.workspace.get_settings", return_value=self.settings)
        )
        self.upload_settings = patch(
            "app.document_storage.get_settings", return_value=self.settings
        )
        self.upload_settings.start()
        self.addCleanup(self.upload_settings.stop)
        self.test_engine = test_engine(self, "sqlite:///:memory:")
        SQLModel.metadata.create_all(self.test_engine)

        def get_test_session():
            with Session(self.test_engine) as session:
                yield session

        app.dependency_overrides[get_session] = get_test_session
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(app.dependency_overrides.pop, get_session)

    def test_01_root_and_health(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("PageIndex Document RAG API", res.json()["name"])

        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_02_collections_crud(self):
        mock_pi = MagicMock()
        mock_pi.create_collection.return_value = {
            "collection": {"id": "pi_coll_123", "name": "Annual Reports"}
        }

        with patch(
            "app.routers.collections.get_pageindex_client", return_value=mock_pi
        ):
            res = self.client.post(
                "/api/v1/collections/", json={"name": "Annual Reports"}
            )
            self.assertEqual(res.status_code, 201)
            coll = res.json()
            self.assertEqual(coll["name"], "Annual Reports")
            self.assertEqual(coll["pageindex_collection_id"], "pi_coll_123")
            coll_id = coll["id"]

            res = self.client.get("/api/v1/collections/")
            self.assertEqual(res.status_code, 200)
            items = res.json()
            self.assertTrue(any(c["id"] == coll_id for c in items))

            res = self.client.get(f"/api/v1/collections/{coll_id}")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["id"], coll_id)

            res = self.client.delete(f"/api/v1/collections/{coll_id}")
            self.assertEqual(res.status_code, 204)

            res = self.client.get(f"/api/v1/collections/{coll_id}")
            self.assertEqual(res.status_code, 404)

    def test_03_documents_flow(self):
        mock_pi_docs = MagicMock()
        mock_pi_docs.submit_document.return_value = {
            "doc_id": "doc_test_999",
            "status": "ready",
        }

        with patch(
            "app.routers.documents.get_pageindex_client", return_value=mock_pi_docs
        ):
            file_content = b"%PDF-1.4 Mock document content"
            files = {
                "file": (
                    "sample_report.pdf",
                    io.BytesIO(file_content),
                    "application/pdf",
                )
            }

            res = self.client.post("/api/v1/documents/", files=files)
            self.assertEqual(res.status_code, 201)
            doc = res.json()
            self.assertEqual(doc["filename"], "sample_report.pdf")
            self.assertEqual(doc["doc_id"], "doc_test_999")
            self.assertEqual(doc["status"], "ready")
            doc_id = doc["id"]

            res = self.client.get("/api/v1/documents/")
            self.assertEqual(res.status_code, 200)
            self.assertTrue(any(d["id"] == doc_id for d in res.json()))

            res = self.client.get(f"/api/v1/documents/{doc_id}")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["filename"], "sample_report.pdf")

            mock_pi_chat = MagicMock()
            mock_pi_chat.chat.return_value = chat_result(
                "The operating margin is 18.5% with growth in Q3."
            )
            mock_pi_chat.get_citations.return_value = [
                {"page": 4, "text": "Operating margin 18.5%"}
            ]

            with patch(
                "app.routers.chat.get_pageindex_client", return_value=mock_pi_chat
            ):
                chat_res = self.client.post(
                    "/api/v1/chat/",
                    json={
                        "question": "What is the operating margin?",
                        "doc_id": "doc_test_999",
                    },
                )
                self.assertEqual(chat_res.status_code, 201)
                chat_data = chat_res.json()
                self.assertIn("18.5%", chat_data["answer"])
                self.assertEqual(chat_data["citations"][0]["page"], 4)
                self.assertEqual(chat_data["usage"]["cached_tokens"], 5)

            hist_res = self.client.get(
                "/api/v1/chat/history", params={"doc_id": "doc_test_999"}
            )
            self.assertEqual(hist_res.status_code, 200)
            self.assertTrue(len(hist_res.json()) >= 1)

            mock_search = MagicMock()
            mock_search.search.return_value = {
                "results": [
                    {
                        "question": "What is operating margin?",
                        "documents": [
                            {
                                "id": "doc_test_999",
                                "pages": [
                                    {
                                        "page": 4,
                                        "relevance": 0.94,
                                        "read": "text",
                                        "text": "Operating margin is 18.5%",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "usage": {"credits": 1},
            }

            with patch(
                "app.routers.search.get_search_client", return_value=mock_search
            ):
                search_res = self.client.post(
                    "/api/v1/search/",
                    json={
                        "questions": ["What is operating margin?"],
                        "document": "doc_test_999",
                    },
                )
                self.assertEqual(search_res.status_code, 200)
                s_data = search_res.json()
                self.assertEqual(len(s_data["results"]), 1)
                found = s_data["results"][0]["documents"][0]
                self.assertEqual(found["doc_id"], "doc_test_999")
                self.assertEqual(found["pages"][0]["page"], 4)

            mock_extract = MagicMock()
            mock_extract.extract.return_value = {
                "id": "job_ext_555",
                "extract_result": {"margin": 18.5, "period": "Q3"},
                "extract_metadata": {"field_metadata": {"/margin": {"page": 4}}},
                "usage": {"credits": 1},
            }

            with patch(
                "app.routers.extract.get_extract_client", return_value=mock_extract
            ):
                ext_res = self.client.post(
                    "/api/v1/extract/",
                    json={
                        "document": "doc_test_999",
                        "schema": {
                            "type": "object",
                            "properties": {"margin": {"type": "number"}},
                        },
                        "schema_name": "Margin Schema",
                    },
                )
                self.assertEqual(ext_res.status_code, 201)
                ext_data = ext_res.json()
                self.assertEqual(ext_data["status"], "completed")
                self.assertEqual(ext_data["result"]["margin"], 18.5)
                job_id = ext_data["id"]

                jobs_res = self.client.get("/api/v1/extract/jobs")
                self.assertEqual(jobs_res.status_code, 200)
                self.assertTrue(any(j["id"] == job_id for j in jobs_res.json()))

                job_res = self.client.get(f"/api/v1/extract/jobs/{job_id}")
                self.assertEqual(job_res.status_code, 200)
                self.assertEqual(job_res.json()["result"]["period"], "Q3")
                self.assertEqual(job_res.json()["usage"], {"credits": 1})
                self.assertEqual(
                    job_res.json()["extract_metadata"]["field_metadata"]["/margin"][
                        "page"
                    ],
                    4,
                )

            del_res = self.client.delete(f"/api/v1/documents/{doc_id}")
            self.assertEqual(del_res.status_code, 204)

            get_del = self.client.get(f"/api/v1/documents/{doc_id}")
            self.assertEqual(get_del.status_code, 404)

    def test_04_batch_documents_flow(self):
        mock_pi_docs = MagicMock()
        mock_pi_docs.submit_document.side_effect = [
            {"doc_id": "doc_batch_1", "status": "ready"},
            {"doc_id": "doc_batch_2", "status": "ready"},
        ]

        with patch(
            "app.routers.documents.get_pageindex_client", return_value=mock_pi_docs
        ):
            files = [
                (
                    "files",
                    ("doc1.pdf", io.BytesIO(b"%PDF-1.4 Doc 1"), "application/pdf"),
                ),
                (
                    "files",
                    ("doc2.pdf", io.BytesIO(b"%PDF-1.4 Doc 2"), "application/pdf"),
                ),
            ]

            res = self.client.post("/api/v1/documents/batch", files=files)
            self.assertEqual(res.status_code, 201)
            docs = res.json()
            self.assertEqual(len(docs), 2)
            self.assertEqual(docs[0]["filename"], "doc1.pdf")
            self.assertEqual(docs[1]["filename"], "doc2.pdf")

    def test_05_chat_sessions_and_context(self):
        mock_pi_chat = MagicMock()
        mock_pi_chat.chat.side_effect = [
            chat_result("Here is the summary of TCS Policy."),
            chat_result(
                "Above I summarized the TCS Occupational Health and Safety Policy."
            ),
        ]
        mock_pi_chat.get_citations.return_value = [
            {"page": 3, "text": "Policy summary"}
        ]

        with patch("app.routers.chat.get_pageindex_client", return_value=mock_pi_chat):
            res_sess = self.client.post(
                "/api/v1/chat/sessions",
                json={"title": "TCS Discussion", "doc_id": "doc_test_100"},
            )
            self.assertEqual(res_sess.status_code, 201)
            session_data = res_sess.json()
            session_id = session_data["id"]
            self.assertEqual(session_data["title"], "TCS Discussion")

            res_chat1 = self.client.post(
                "/api/v1/chat/",
                json={
                    "session_id": session_id,
                    "question": "Can you summarize the policy?",
                    "doc_id": "doc_test_100",
                },
            )
            self.assertEqual(res_chat1.status_code, 201)
            self.assertIn("Here is the summary", res_chat1.json()["answer"])
            self.assertEqual(res_chat1.json()["session_id"], session_id)

            res_chat2 = self.client.post(
                "/api/v1/chat/",
                json={
                    "session_id": session_id,
                    "question": "just let me know what you just response me above",
                    "messages": [{"role": "user", "content": "Ignored client history"}],
                    "doc_id": "doc_test_100",
                },
            )
            self.assertEqual(res_chat2.status_code, 201)
            self.assertIn("Above I summarized", res_chat2.json()["answer"])

            last_call_args = mock_pi_chat.chat.call_args[0][0]
            self.assertIsInstance(last_call_args, list)
            self.assertEqual(len(last_call_args), 3)
            self.assertEqual(last_call_args[0]["role"], "user")
            self.assertEqual(
                last_call_args[1],
                {"role": "assistant", "content": "Here is the summary of TCS Policy."},
            )
            self.assertEqual(last_call_args[2]["role"], "user")

            res_detail = self.client.get(f"/api/v1/chat/sessions/{session_id}")
            self.assertEqual(res_detail.status_code, 200)
            detail = res_detail.json()
            self.assertEqual(len(detail["messages"]), 2)

            res_sessions = self.client.get("/api/v1/chat/sessions")
            self.assertEqual(res_sessions.status_code, 200)
            listed = next(s for s in res_sessions.json() if s["id"] == session_id)
            self.assertEqual(listed["message_count"], 4)
            self.assertEqual(
                listed["last_message_preview"],
                "Above I summarized the TCS Occupational Health and Safety Policy.",
            )

            del_res = self.client.delete(f"/api/v1/chat/sessions/{session_id}")
            self.assertEqual(del_res.status_code, 204)

            check_del = self.client.get(f"/api/v1/chat/sessions/{session_id}")
            self.assertEqual(check_del.status_code, 404)
            response = self.client.get(
                "/api/v1/chat/history", params={"session_id": session_id}
            )
            self.assertEqual(response.json(), [])
            response = self.client.post(
                "/api/v1/chat/", json={"session_id": session_id, "question": "Continue"}
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(mock_pi_chat.chat.call_count, 2)

    def test_06_trash_and_extract_clear(self):
        res_trash_init = self.client.get("/api/v1/trash/items")
        self.assertEqual(res_trash_init.status_code, 200)

        res_sess = self.client.post(
            "/api/v1/chat/sessions", json={"title": "Trash Chat Test"}
        )
        self.assertEqual(res_sess.status_code, 201)
        sess_id = res_sess.json()["id"]

        del_sess = self.client.delete(f"/api/v1/chat/sessions/{sess_id}")
        self.assertEqual(del_sess.status_code, 204)

        res_trash = self.client.get("/api/v1/trash/items")
        self.assertEqual(res_trash.status_code, 200)
        items = res_trash.json()
        self.assertTrue(
            any(it["id"] == sess_id and it["type"] == "chat" for it in items)
        )

        restore_res = self.client.post(
            "/api/v1/trash/restore",
            json={"items": [{"id": sess_id, "type": "chat"}]},
        )
        self.assertEqual(restore_res.status_code, 200)
        self.assertEqual(restore_res.json()["restored"], 1)

        check_restored = self.client.get(f"/api/v1/chat/sessions/{sess_id}")
        self.assertEqual(check_restored.status_code, 200)

        del_again = self.client.delete(f"/api/v1/chat/sessions/{sess_id}")
        self.assertEqual(del_again.status_code, 204)

        perm_del = self.client.post(
            "/api/v1/trash/permanent-delete",
            json={"items": [{"id": sess_id, "type": "chat"}]},
        )
        self.assertEqual(perm_del.status_code, 200)
        self.assertEqual(perm_del.json()["deleted"], 1)

        clear_ext = self.client.delete("/api/v1/extract/jobs")
        self.assertEqual(clear_ext.status_code, 200)

        empty_res = self.client.delete("/api/v1/trash/empty")
        self.assertEqual(empty_res.status_code, 200)

    def test_upload_validation_precedes_storage_and_provider(self):
        with (
            patch(
                "app.routers.documents.get_settings",
                return_value=Settings(max_upload_size_mb=1),
            ),
            patch("app.routers.documents.get_pageindex_client") as provider,
        ):
            invalid = self.client.post(
                "/api/v1/documents/batch",
                files=[
                    ("files", ("report.pdf", pdf_bytes(1))),
                    ("files", ("wrong.pdf", b"invalid")),
                ],
            )
            self.assertEqual(invalid.status_code, 415)
            oversized = self.client.post(
                "/api/v1/documents/",
                files={"file": ("large.pdf", b"%PDF-" + b"x" * 1024**2)},
            )
            self.assertEqual(oversized.status_code, 413)
            invalid_metadata = self.client.post(
                "/api/v1/documents/",
                params={"metadata": "[]"},
                files={"file": ("report.pdf", pdf_bytes(1))},
            )
            self.assertEqual(invalid_metadata.status_code, 400)
            provider.assert_not_called()
        self.assertEqual(list(self.settings.upload_dir.iterdir()), [])

    def test_equal_filenames_have_separate_previews_and_purge(self):
        provider = MagicMock()
        provider.submit_document.side_effect = [
            {"doc_id": "first"},
            {"doc_id": "second"},
        ]
        provider.get_page_content.return_value = []
        with (
            patch("app.routers.documents.get_pageindex_client", return_value=provider),
            patch("app.routers.trash.get_pageindex_client", return_value=provider),
        ):
            response = self.client.post(
                "/api/v1/documents/batch",
                files=[("files", ("report.pdf", pdf_bytes(n))) for n in (1, 2)],
            )
            self.assertEqual(response.status_code, 201, response.text)
            first, second = response.json()
            first_url = f"/api/v1/documents/{first['id']}"
            invalid = self.client.patch(first_url, json={"filename": "../report.pdf"})
            self.assertEqual(invalid.status_code, 422)
            for name in ("Revised report", "Final report.PDF"):
                renamed = self.client.patch(first_url, json={"filename": name})
                self.assertEqual(renamed.status_code, 200, renamed.text)
                self.assertEqual(
                    renamed.json()["filename"],
                    name if name.endswith(".PDF") else f"{name}.pdf",
                )
                self.assertEqual(renamed.json()["doc_id"], "first")
            old_citation = self.client.get(
                "/api/v1/documents/page-preview",
                params={"doc_id": f"{first['id']}_report.pdf"},
            )
            self.assertEqual(old_citation.status_code, 200, old_citation.text)
            self.assertEqual(old_citation.json()["filename"], "Final report.PDF")
            for document, total in ((first, 1), (second, 2)):
                preview = self.client.get(
                    "/api/v1/documents/page-preview",
                    params={"doc_id": document["doc_id"]},
                )
                self.assertEqual(preview.status_code, 200, preview.text)
                self.assertEqual(preview.json()["total_pages"], total)
                image = self.client.get(preview.json()["image_url"])
                self.assertEqual(image.status_code, 200, image.text[:100])
                self.assertEqual(image.headers["content-type"], "image/jpeg")
            missing = self.client.get(
                "/api/v1/documents/page-image", params={"doc_id": "first", "page": 2}
            )
            self.assertEqual(missing.status_code, 404)
            purge = {"items": [{"type": "document", "id": first["id"]}]}
            self.assertEqual(
                self.client.post("/api/v1/trash/permanent-delete", json=purge).json(),
                {"deleted": 0},
            )
            provider.delete_document.assert_not_called()
            self.assertEqual(
                self.client.delete(f"/api/v1/documents/{first['id']}").status_code, 204
            )
            trashed_rename = self.client.patch(first_url, json={"filename": "Archived"})
            self.assertEqual(trashed_rename.status_code, 404)
            hidden = self.client.get(
                "/api/v1/documents/page-preview", params={"doc_id": "first"}
            )
            self.assertEqual(hidden.status_code, 404)
            self.assertEqual(
                self.client.post("/api/v1/trash/permanent-delete", json=purge).json(),
                {"deleted": 1},
            )
            provider.delete_document.assert_called_once_with("first")
            self.assertEqual(
                [path.name for path in self.settings.upload_dir.iterdir()],
                [f"{second['id']}_report.pdf"],
            )

    def test_chat_budget_and_model_are_enforced(self):
        with Session(self.test_engine) as session:
            conversation = ChatSession()
            session.add(conversation)
            session.flush()
            conversation_id = conversation.id
            session.add_all(
                [
                    ChatHistory(
                        session_id=conversation_id, question="old", answer="x" * 100
                    ),
                    ChatHistory(
                        session_id=conversation_id, question="new", answer="short"
                    ),
                ]
            )
            session.commit()
        provider = MagicMock()
        provider.chat.return_value = chat_result("Answer")
        provider.get_citations.return_value = []
        settings = Settings(
            _env_file=None, chat_history_max_bytes=20, chat_allowed_models=["approved"]
        )
        with (
            patch("app.routers.chat.get_settings", return_value=settings),
            patch("app.routers.chat.get_pageindex_client", return_value=provider),
        ):
            response = self.client.post(
                "/api/v1/chat/", json={"question": "Follow up", "model": "unapproved"}
            )
            self.assertEqual(response.status_code, 422)
            provider.chat.assert_not_called()
            response = self.client.post(
                "/api/v1/chat/",
                json={
                    "session_id": conversation_id,
                    "question": "Follow up",
                    "model": "approved",
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            prompt = provider.chat.call_args.args[0]
            self.assertEqual(
                [message["content"] for message in prompt],
                ["new", "short", "Follow up"],
            )
            self.assertEqual(provider.chat.call_args.kwargs["model"], "approved")
            self.assertEqual(response.json()["usage"]["total_tokens"], 30)

    def test_extract_rejects_unknown_document_before_provider_call(self):
        with patch("app.routers.extract.get_extract_client") as provider:
            response = self.client.post(
                "/api/v1/extract/",
                json={"document": "missing", "schema": {"type": "object"}},
            )
            self.assertEqual(response.status_code, 404)
            provider.assert_not_called()

    def test_collection_upload_and_chat_use_provider_collection_id(self):
        provider = MagicMock()
        provider.create_collection.return_value = {
            "collection": {"id": "provider-collection"}
        }
        provider.submit_document.return_value = {"doc_id": "provider-document"}
        provider.chat.return_value = chat_result("Collection answer")
        provider.get_citations.return_value = []
        with (
            patch(
                "app.routers.collections.get_pageindex_client", return_value=provider
            ),
            patch("app.routers.documents.get_pageindex_client", return_value=provider),
            patch("app.routers.chat.get_pageindex_client", return_value=provider),
        ):
            collection = self.client.post(
                "/api/v1/collections/", json={"name": "Reports"}
            )
            self.assertEqual(collection.status_code, 201)
            collection_id = collection.json()["id"]
            response = self.client.post(
                "/api/v1/documents/",
                params={"collection_id": collection_id},
                files={"file": ("report.pdf", pdf_bytes(1))},
            )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(
                provider.submit_document.call_args.kwargs["collection_id"],
                "provider-collection",
            )
            response = self.client.post(
                "/api/v1/chat/",
                json={
                    "collection_id": collection_id,
                    "question": "What is in this collection?",
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(
                provider.chat.call_args.kwargs["collection_id"], "provider-collection"
            )
            follow_up = self.client.post(
                "/api/v1/chat/",
                json={
                    "session_id": response.json()["session_id"],
                    "doc_id": "another-document",
                    "question": "Continue",
                },
            )
            self.assertEqual(follow_up.status_code, 409)
            provider.chat.assert_called_once()

    def test_pending_extraction_updates_and_hides_deleted_job(self):
        provider = MagicMock()
        provider.extract.return_value = {"id": "extract-1", "status": "running"}
        provider.get_extract.return_value = {
            "status": "completed",
            "extract_result": [{"value": 42}],
            "usage": {"credits": 2},
        }
        index = MagicMock()
        index.submit_document.return_value = {"doc_id": "source"}
        with (
            patch("app.routers.documents.get_pageindex_client", return_value=index),
            patch("app.routers.extract.get_extract_client", return_value=provider),
        ):
            upload = self.client.post(
                "/api/v1/documents/", files={"file": ("report.pdf", pdf_bytes(1))}
            )
            self.assertEqual(upload.status_code, 201)
            response = self.client.post(
                "/api/v1/extract/",
                json={"document": "source", "schema": {"type": "array"}},
            )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["status"], "running")
            path = f"/api/v1/extract/jobs/{response.json()['id']}"
            completed = self.client.get(path)
            self.assertEqual(completed.json()["result"], [{"value": 42}])
            self.assertEqual(completed.json()["usage"], {"credits": 2})
            self.assertEqual(self.client.delete(path).status_code, 204)
            self.assertEqual(self.client.get(path).status_code, 404)
            provider.get_extract.assert_called_once_with("extract-1")

    def test_legacy_citation_name_resolves_only_verified_provider_file(self):
        stored_name = f"{uuid4()}_report.pdf"
        (self.settings.upload_dir / stored_name).write_bytes(pdf_bytes(2))
        (self.settings.upload_dir / f"{uuid4()}_report.pdf").write_bytes(pdf_bytes(1))
        with Session(self.test_engine) as session:
            session.add(
                Document(doc_id="legacy", filename="report.pdf", status="ready")
            )
            session.commit()

        provider = MagicMock()
        provider.get_document_id.return_value = "legacy"
        provider.get_document.return_value = {"name": stored_name, "pageNum": 2}
        provider.get_page_content.return_value = []
        with patch("app.routers.documents.get_pageindex_client", return_value=provider):
            response = self.client.get(
                "/api/v1/documents/page-preview",
                params={"doc_id": f"folder/{stored_name}", "page": 2},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["doc_id"], "legacy")
            self.assertEqual(response.json()["total_pages"], 2)
            unknown = self.client.get(
                "/api/v1/documents/page-preview",
                params={"doc_id": "unmatched-report.pdf"},
            )
            self.assertEqual(unknown.status_code, 404)

    def test_truncated_chat_is_retried_before_saving_citations_and_usage(self):
        provider = MagicMock()
        complete = 'The policy requires reviews. <cite doc="policy.pdf" page="4" />'
        provider.chat.side_effect = [
            chat_result('Partial answer <cite doc="policy.pdf" page="4', "length"),
            chat_result(complete),
        ]
        provider.get_citations.return_value = [{"page": 4, "doc_id": "policy"}]
        with (
            patch("app.routers.chat.get_pageindex_client", return_value=provider),
            patch("app.routers.chat.get_settings", return_value=self.settings),
        ):
            response = self.client.post(
                "/api/v1/chat",
                json={"question": "Explain the policy", "doc_id": "policy"},
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["answer"], complete)
        self.assertEqual(
            response.json()["citations"], [{"page": 4, "doc_id": "policy"}]
        )
        self.assertEqual(response.json()["usage"]["total_tokens"], 60)
        first, retry = provider.chat.call_args_list
        self.assertEqual(first.args, retry.args)
        self.assertEqual(retry.kwargs["doc_id"], "policy")
        self.assertEqual(first.kwargs["extra_body"]["max_tokens"], 4096)
        self.assertEqual(retry.kwargs["extra_body"]["max_tokens"], 8192)
        self.assertIn("complete answer", retry.kwargs["instructions"])
        provider.get_citations.assert_called_once_with(complete, doc_id="policy")
        saved = self.client.get("/api/v1/chat/history").json()
        self.assertEqual([record["answer"] for record in saved], [complete])

    def test_chat_retry_respects_configured_cap_and_does_not_save_partial_output(self):
        provider = MagicMock()
        provider.chat.return_value = chat_result("An incomplete answer", "max_tokens")
        settings = self.settings.model_copy(update={"chat_output_tokens": 1200})
        with (
            patch("app.routers.chat.get_pageindex_client", return_value=provider),
            patch("app.routers.chat.get_settings", return_value=settings),
        ):
            response = self.client.post(
                "/api/v1/chat", json={"question": "Explain everything"}
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(provider.chat.call_args_list), 2)
        for call in provider.chat.call_args_list:
            self.assertEqual(call.kwargs["extra_body"]["max_tokens"], 1200)
        provider.get_citations.assert_not_called()
        self.assertEqual(self.client.get("/api/v1/chat/history").json(), [])
        self.assertEqual(self.client.get("/api/v1/chat/sessions").json(), [])
        self.assertEqual(
            self.client.get("/api/v1/workspace/usage").json()["chat_tokens"], 60
        )


if __name__ == "__main__":
    unittest.main()
