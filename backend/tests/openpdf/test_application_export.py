from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.config import Settings
from backend.main import create_app
from backend.openpdf import OpenPdfRuntime, OpenPdfWorkerExportEngine
from backend.service import AssignmentApplicationService
from backend.storage import LocalObjectStore, export_manifest_object_key
from backend.tests.document.factories import worksheet_pdf

ORIGIN = "http://testserver"
HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
OWNER_SECRET = "openpdf-application-owner-secret-A7xQ4mZ8pL3sK5wN"  # noqa: S105
REVIEW_SECRET = "openpdf-application-review-secret-R2tY7uI4oP8dF5hJ"  # noqa: S105
FAKE_WORKER = Path(__file__).resolve().parent / "helpers" / "fake_worker.py"


def _settings(path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "storage_backend": "local",
        "local_storage_path": path,
        "public_origin": ORIGIN,
        "cookie_secret": OWNER_SECRET,
        "review_token_secret": REVIEW_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


def _create(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v2/assignments",
        files={
            "file": (
                "openpdf-application-fixture.pdf",
                worksheet_pdf(
                    questions=(
                        "1. Why do plants need sunlight?",
                        "2. How does sunlight help a plant make food?",
                        "3. How can photosynthesis support other living things?",
                    )
                ),
                "application/pdf",
            )
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm(
    client: TestClient,
    assignment: dict[str, object],
    question_index: int,
    text: str,
) -> dict[str, object]:
    questions = assignment["questions"]
    assert isinstance(questions, list)
    question_id = questions[question_index]["question_id"]
    assignment_id = assignment["assignment_id"]
    candidate = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        json={
            "assignment_version": assignment["version"],
            "text": text,
            "origin": "student_verbatim",
            "interaction": {"kind": "direct_typed"},
        },
        headers=HEADERS,
    )
    assert candidate.status_code == 200, candidate.text
    candidate_body = candidate.json()
    review = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        json={
            "assignment_version": candidate_body["version"],
            "candidate_id": candidate_body["candidate"]["candidate_id"],
            "candidate_version": candidate_body["candidate"]["candidate_version"],
        },
        headers=HEADERS,
    )
    assert review.status_code == 200, review.text
    review_body = review.json()
    confirmation = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": review_body["version"],
            "review_token": review_body["review_token"],
            "candidate_id": review_body["candidate"]["candidate_id"],
            "candidate_version": review_body["candidate"]["candidate_version"],
        },
        headers=HEADERS,
    )
    assert confirmation.status_code == 200, confirmation.text
    result = confirmation.json()
    assignment["version"] = result["version"]
    return result


def test_normal_application_factory_endpoint_exports_with_openpdf(
    tmp_path: Path,
    openpdf_worker_jar: Path,
    qpdf_executable: Path,
) -> None:
    settings = _settings(
        tmp_path / "objects",
        pdf_engine="openpdf",
        openpdf_jar_path=openpdf_worker_jar,
        openpdf_qpdf_path=qpdf_executable,
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        assignment = _create(client)
        assignment_id = assignment["assignment_id"]
        source_before = client.get(f"/api/v2/assignments/{assignment_id}/source").content
        inline = "The office is efficient; its official file records café and résumé details."
        long = (
            "A different office keeps every approved character, coordinate, and source page exact. "
            * 80
        ).strip()
        inline_confirmation = _confirm(client, assignment, 0, inline)
        appendix_confirmation = _confirm(client, assignment, 1, long)
        assert inline_confirmation["confirmed_answer"]["placement"] == "inline"
        assert appendix_confirmation["confirmed_answer"]["placement"] == "appendix"

        questions = assignment["questions"]
        assert isinstance(questions, list)
        draft_question = questions[2]["question_id"]
        draft = client.post(
            f"/api/v2/assignments/{assignment_id}/questions/{draft_question}/candidates",
            json={
                "assignment_version": assignment["version"],
                "text": "UNCONFIRMED-DRAFT-MUST-NOT-EXPORT",
                "origin": "student_verbatim",
                "interaction": {"kind": "direct_typed"},
            },
            headers=HEADERS,
        )
        assert draft.status_code == 200, draft.text
        assignment["version"] = draft.json()["version"]

        exported = client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": assignment["version"],
                "idempotency_key": "openpdf-application-export-0001",
            },
            headers=HEADERS,
        )
        assert exported.status_code == 201, exported.text
        download = client.get(exported.json()["download_url"])
        assert download.status_code == 200
        extracted = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(download.content)).pages
        )
        assert inline in extracted
        assert "A different office keeps" in extracted
        assert "UNCONFIRMED-DRAFT-MUST-NOT-EXPORT" not in extracted
        source_after = client.get(f"/api/v2/assignments/{assignment_id}/source").content
        assert hashlib.sha256(source_after).digest() == hashlib.sha256(source_before).digest()

        engine = app.state.assignment_service.document_executor
        assert isinstance(engine, OpenPdfWorkerExportEngine)
        assert engine.engine_name == "openpdf"
        assert [process.label for process in engine.last_evidence.processes] == [
            "openpdf",
            "qpdf",
            "pdfbox",
        ]
        stored_manifest = app.state.assignment_service.store.read(
            export_manifest_object_key(assignment_id, exported.json()["export_id"])
        )
        assert json.loads(stored_manifest.data)["exporter_version"] == "claros-openpdf-v1"
        assert engine.last_job_path is not None and not engine.last_job_path.exists()

        if os.getenv("CLAROS_PDFJS_RELEASE_CHECK") == "1":
            node = shutil.which("node")
            assert node is not None, "PDF.js release validation requires Node"
            completed_path = tmp_path / "completed-openpdf.pdf"
            expectations_path = tmp_path / "pdfjs-expectations.json"
            completed_path.write_bytes(download.content)
            expectations_path.write_text(
                json.dumps(
                    {
                        "source_pages": 1,
                        "answers": [
                            {"placement": "inline", "source_page": 1, "exact_text": inline},
                            {"placement": "appendix", "source_page": 1, "exact_text": long},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            compatibility = subprocess.run(  # noqa: S603
                [
                    node,
                    "scripts/validate-openpdf-pdfjs.mjs",
                    str(completed_path),
                    str(expectations_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            assert compatibility.returncode == 0, compatibility.stdout.decode(
                "utf-8", errors="replace"
            )


@pytest.mark.parametrize(
    ("mode", "expected_status", "expected_code", "timeout"),
    (
        ("crash", 503, "publish_failed", 5.0),
        ("timeout", 503, "export_timeout", 2.0),
        ("malformed", 503, "publish_failed", 5.0),
        ("mutate-contract", 503, "publish_failed", 5.0),
        ("copy-source", 422, "invalid_export", 15.0),
        ("invalid-pdf", 422, "invalid_export", 5.0),
        ("oversize", 422, "invalid_export", 5.0),
        ("wrong-coordinate", 422, "invalid_export", 15.0),
        ("wrong-text", 422, "invalid_export", 15.0),
        ("validator-fail", 422, "invalid_export", 15.0),
    ),
)
def test_worker_or_validator_failure_blocks_publication_and_preserves_confirmation(
    tmp_path: Path,
    openpdf_worker_jar: Path,
    qpdf_executable: Path,
    mode: str,
    expected_status: int,
    expected_code: str,
    timeout: float,
) -> None:
    settings = _settings(tmp_path / "objects")
    work_root = tmp_path / "jobs"
    work_root.mkdir()
    engine = OpenPdfWorkerExportEngine(
        runtime=OpenPdfRuntime(
            jar_path=openpdf_worker_jar,
            qpdf_path=qpdf_executable,
            work_root=work_root,
            max_output_bytes=2 * 1024 * 1024,
            worker_command_override=(
                None if mode == "validator-fail" else (sys.executable, str(FAKE_WORKER), mode)
            ),
            pdfbox_command_override=(
                (sys.executable, str(FAKE_WORKER), mode) if mode == "validator-fail" else None
            ),
        )
    )
    service = AssignmentApplicationService(
        settings=settings,
        store=LocalObjectStore(settings.local_storage_path),
        document_executor=engine,  # type: ignore[arg-type]
        document_timeout_seconds=max(timeout, 15.0),
    )
    app = create_app(settings=settings, assignment_service=service)

    with TestClient(app) as client:
        assignment = _create(client)
        exact = "The confirmed office answer survives export failure."
        _confirm(client, assignment, 0, exact)
        service._document_timeout_seconds = timeout
        failed = client.post(
            f"/api/v2/assignments/{assignment['assignment_id']}/exports",
            json={
                "assignment_version": assignment["version"],
                "idempotency_key": f"failure-{mode}-export-0001",
            },
            headers=HEADERS,
        )
        assert failed.status_code == expected_status, failed.text
        assert failed.json()["error"]["code"] == expected_code
        restored = client.get(f"/api/v2/assignments/{assignment['assignment_id']}").json()
        assert restored["questions"][0]["confirmed_answer"]["exact_text"] == exact
        assert engine.active_process_count == 0
        assert engine.last_job_path is not None and not engine.last_job_path.exists()
