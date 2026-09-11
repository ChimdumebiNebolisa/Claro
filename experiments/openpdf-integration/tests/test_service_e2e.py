# ruff: noqa: S101

from __future__ import annotations

import hashlib
import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpdf_integration.adapter import OpenPdfWorkerExportEngine, SpikeRuntime
from pypdf import PdfReader

from backend.config import Settings
from backend.main import create_app
from backend.service import AssignmentApplicationService
from backend.storage import LocalObjectStore

ROOT = Path(__file__).resolve().parents[1]
FAKE_WORKER = ROOT / "tests" / "helpers" / "fake_worker.py"
ORIGIN = "http://testserver"
HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
OWNER_SECRET = "openpdf-spike-owner-secret-with-sufficient-entropy"  # noqa: S105
REVIEW_SECRET = "openpdf-spike-review-secret-with-sufficient-entropy"  # noqa: S105


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        storage_backend="local",
        local_storage_path=path,
        public_origin=ORIGIN,
        cookie_secret=OWNER_SECRET,
        review_token_secret=REVIEW_SECRET,
    )


def _client(tmp_path: Path, engine: OpenPdfWorkerExportEngine) -> TestClient:
    settings = _settings(tmp_path / "objects")
    service = AssignmentApplicationService(
        settings=settings,
        store=LocalObjectStore(settings.local_storage_path),
        document_executor=engine,  # type: ignore[arg-type]
    )
    return TestClient(create_app(settings=settings, assignment_service=service))


def _confirm(client: TestClient, assignment: dict, question_index: int, text: str) -> dict:
    assignment_id = assignment["assignment_id"]
    question_id = assignment["questions"][question_index]["question_id"]
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
    body = candidate.json()
    review = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        json={
            "assignment_version": body["version"],
            "candidate_id": body["candidate"]["candidate_id"],
            "candidate_version": body["candidate"]["candidate_version"],
        },
        headers=HEADERS,
    )
    assert review.status_code == 200, review.text
    reviewed = review.json()
    confirmation = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": reviewed["version"],
            "review_token": reviewed["review_token"],
            "candidate_id": reviewed["candidate"]["candidate_id"],
            "candidate_version": reviewed["candidate"]["candidate_version"],
        },
        headers=HEADERS,
    )
    assert confirmation.status_code == 200, confirmation.text
    result = confirmation.json()
    assignment["version"] = result["version"]
    return result


def _create(client: TestClient) -> dict:
    response = client.post(
        "/api/v2/assignments",
        data={"sample_id": "biology-short-answer"},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_real_claros_commit_to_quarantine_validation_to_derivative(tmp_path: Path) -> None:
    work = tmp_path / "jobs"
    work.mkdir()
    engine = OpenPdfWorkerExportEngine(runtime=SpikeRuntime(work_root=work))
    with _client(tmp_path, engine) as client:
        assignment = _create(client)
        assignment_id = assignment["assignment_id"]
        source_before = client.get(f"/api/v2/assignments/{assignment_id}/source").content
        inline = "The office is efficient; official files remain exact (100%)."
        long = (
            "A different office keeps every approved character, coordinate, and source page exact. "
            * 80
        ).strip()
        _confirm(client, assignment, 0, inline)
        _confirm(client, assignment, 1, long)

        draft_id = assignment["questions"][2]["question_id"]
        draft = client.post(
            f"/api/v2/assignments/{assignment_id}/questions/{draft_id}/candidates",
            json={
                "assignment_version": assignment["version"],
                "text": "UNCOMMITTED-DRAFT-SENTINEL",
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
                "idempotency_key": "openpdf-e2e-export-0001",
            },
            headers=HEADERS,
        )
        assert exported.status_code == 201, exported.text
        download = client.get(exported.json()["download_url"])
        assert download.status_code == 200
        text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(download.content)).pages
        )
        assert inline in text
        assert "A different office keeps" in text
        assert "UNCOMMITTED-DRAFT-SENTINEL" not in text
        assert hashlib.sha256(client.get(
            f"/api/v2/assignments/{assignment_id}/source"
        ).content).digest() == hashlib.sha256(source_before).digest()
        assert engine.last_job_path is not None and not engine.last_job_path.exists()
        assert engine.last_evidence.validation_ms > 0


@pytest.mark.parametrize(
    ("mode", "expected_status", "expected_code", "timeout"),
    (
        ("crash", 503, "publish_failed", 5.0),
        ("timeout", 503, "export_timeout", 0.15),
        ("copy-source", 422, "invalid_export", 15.0),
    ),
)
def test_worker_or_validator_failure_preserves_committed_state(
    tmp_path: Path,
    mode: str,
    expected_status: int,
    expected_code: str,
    timeout: float,
) -> None:
    work = tmp_path / "jobs"
    work.mkdir()
    runtime = SpikeRuntime(
        work_root=work,
        worker_command_override=(sys.executable, str(FAKE_WORKER), mode),
    )
    engine = OpenPdfWorkerExportEngine(runtime=runtime)
    client = _client(tmp_path, engine)
    with client:
        assignment = _create(client)
        exact = "The committed office answer must survive renderer failure."
        _confirm(client, assignment, 0, exact)
        client.app.state.assignment_service._document_timeout_seconds = timeout
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
