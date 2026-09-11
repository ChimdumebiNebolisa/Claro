"""Focused API/service branch matrix for the Gate 3 application boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.service as service_module
from backend.api.models import (
    Candidate,
    CandidateOrigin,
    RealtimeCredentialResponse,
    RephraseResponse,
    StudentAttribution,
)
from backend.config import Settings
from backend.document import DocumentEngineError
from backend.document_execution import DocumentExecutionTimeout
from backend.domain import RephraseRecord
from backend.main import create_app
from backend.service import AssignmentApplicationService
from backend.storage import LocalObjectStore

ORIGIN = "http://testserver"
MUTATION_HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
OWNER_TEST_SECRET = "matrix-owner-secret-with-sufficient-entropy"  # noqa: S105
REVIEW_TEST_SECRET = "matrix-review-secret-with-sufficient-entropy"  # noqa: S105
EPHEMERAL_TEST_SECRET = "ephemeral-secret"  # noqa: S105
NOW = datetime(2040, 1, 1, tzinfo=UTC)
SAMPLE_PDF = (
    Path(__file__).resolve().parents[3] / "public" / "fixtures" / "claros-biology-short-answer.pdf"
)


@dataclass
class MutableClock:
    value: datetime = NOW

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@dataclass
class Harness:
    settings: Settings
    store: LocalObjectStore
    service: AssignmentApplicationService
    client: TestClient
    clock: MutableClock


def _settings(storage_root: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "storage_backend": "local",
        "local_storage_path": storage_root,
        "public_origin": ORIGIN,
        "cookie_secret": OWNER_TEST_SECRET,
        "review_token_secret": REVIEW_TEST_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def harness(tmp_path: Path) -> Any:
    settings = _settings(tmp_path / "objects")
    clock = MutableClock()
    store = LocalObjectStore(settings.local_storage_path)
    service = AssignmentApplicationService(settings=settings, store=store, now=clock)
    with TestClient(create_app(settings=settings, assignment_service=service)) as client:
        yield Harness(settings, store, service, client, clock)


def _assert_error(response: Any, status_code: int, code: str) -> None:
    assert response.status_code == status_code, response.text
    assert response.json()["error"]["code"] == code


def _create_sample(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v2/assignments",
        data={"sample_id": "biology-short-answer"},
        headers=MUTATION_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _post_candidate(
    client: TestClient,
    *,
    assignment_id: str,
    question_id: str,
    version: int,
    text: str,
    origin: str,
    interaction: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        json={
            "assignment_version": version,
            "text": text,
            "origin": origin,
            "interaction": interaction,
        },
        headers=MUTATION_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _review_candidate(
    client: TestClient,
    *,
    assignment_id: str,
    question_id: str,
    version: int,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        json={
            "assignment_version": version,
            "candidate_id": candidate["candidate_id"],
            "candidate_version": candidate["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _confirm_review(
    client: TestClient,
    *,
    assignment_id: str,
    question_id: str,
    review: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": review["version"],
            "review_token": review["review_token"],
            "candidate_id": review["candidate"]["candidate_id"],
            "candidate_version": review["candidate"]["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _answer_first_question(harness: Harness) -> tuple[dict[str, Any], dict[str, Any]]:
    assignment = _create_sample(harness.client)
    question = assignment["questions"][0]
    candidate_payload = _post_candidate(
        harness.client,
        assignment_id=assignment["assignment_id"],
        question_id=question["question_id"],
        version=assignment["version"],
        text="Plants use sunlight to make glucose.",
        origin="student_verbatim",
        interaction={"kind": "direct_typed"},
    )
    review = _review_candidate(
        harness.client,
        assignment_id=assignment["assignment_id"],
        question_id=question["question_id"],
        version=candidate_payload["version"],
        candidate=candidate_payload["candidate"],
    )
    confirmation = _confirm_review(
        harness.client,
        assignment_id=assignment["assignment_id"],
        question_id=question["question_id"],
        review=review,
    )
    return assignment, confirmation


def test_upload_validation_timeout_and_context_matrix(
    harness: Harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = harness.client
    pdf_bytes = SAMPLE_PDF.read_bytes()

    _assert_error(
        client.post("/api/v2/assignments", headers=MUTATION_HEADERS),
        422,
        "invalid_assignment_input",
    )
    _assert_error(
        client.post(
            "/api/v2/assignments",
            data={"sample_id": "biology-short-answer"},
            files={"file": ("worksheet.pdf", pdf_bytes, "application/pdf")},
            headers=MUTATION_HEADERS,
        ),
        422,
        "invalid_assignment_input",
    )
    _assert_error(
        client.post(
            "/api/v2/assignments",
            data={"sample_id": "missing-sample"},
            headers=MUTATION_HEADERS,
        ),
        404,
        "sample_not_found",
    )
    _assert_error(
        client.post(
            "/api/v2/assignments",
            files={"file": ("worksheet.txt", b"plain text", "text/plain")},
            headers=MUTATION_HEADERS,
        ),
        415,
        "unsupported_media_type",
    )
    broken = client.post(
        "/api/v2/assignments",
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
        headers=MUTATION_HEADERS,
    )
    assert broken.status_code == 201
    assert broken.json()["status"] == "analysis_failed"
    assert broken.json()["warnings"][0]["code"] == "invalid_pdf_signature"

    async def time_out(*_args: Any, **_kwargs: Any) -> Any:
        raise DocumentExecutionTimeout

    with monkeypatch.context() as scoped:
        scoped.setattr(harness.service.document_executor, "analyze", time_out)
        timed_out = client.post(
            "/api/v2/assignments",
            files={"file": ("slow.pdf", pdf_bytes, "application/pdf")},
            headers=MUTATION_HEADERS,
        )
        assert timed_out.status_code == 201
        assert timed_out.json()["status"] == "analysis_failed"
        assert timed_out.json()["warnings"][0]["code"] == "analysis_timeout"

    created_response = client.post(
        "/api/v2/assignments",
        files={"file": ("student-notes", pdf_bytes, "application/octet-stream")},
        headers=MUTATION_HEADERS,
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    assert created["source"]["filename"] == "student-notes.pdf"
    assignment_id = created["assignment_id"]
    question = created["questions"][0]

    fetched = client.get(f"/api/v2/assignments/{assignment_id}")
    assert fetched.status_code == 200
    assert fetched.headers["etag"] == f'"assignment-version-{created["version"]}"'

    context = client.get(
        f"/api/v2/assignments/{assignment_id}/pages/{question['page_number']}/context",
        params={"question_id": question["question_id"]},
    )
    assert context.status_code == 200, context.text
    assert context.json()["source_status"] == "original"
    assert context.json()["crop"]["width_mpt"] > 0

    _assert_error(
        client.get(
            f"/api/v2/assignments/{assignment_id}/pages/{question['page_number'] + 1}/context",
            params={"question_id": question["question_id"]},
        ),
        404,
        "question_not_found",
    )

    tiny_settings = _settings(tmp_path / "tiny-objects", max_upload_bytes=4)
    with TestClient(create_app(settings=tiny_settings)) as tiny_client:
        _assert_error(
            tiny_client.post(
                "/api/v2/assignments",
                files={"file": ("large.pdf", b"%PDF-", "application/pdf")},
                headers=MUTATION_HEADERS,
            ),
            413,
            "file_too_large",
        )

    limited_settings = _settings(
        tmp_path / "limited-objects",
        upload_rate_limit=1,
        upload_rate_window_seconds=60,
    )
    with TestClient(create_app(settings=limited_settings)) as limited_client:
        _assert_error(
            limited_client.post(
                "/api/v2/assignments",
                data={"sample_id": "missing-sample"},
                headers=MUTATION_HEADERS,
            ),
            404,
            "sample_not_found",
        )
        _assert_error(
            limited_client.post(
                "/api/v2/assignments",
                data={"sample_id": "missing-sample"},
                headers=MUTATION_HEADERS,
            ),
            429,
            "rate_limit_exceeded",
        )


def test_candidate_review_confirmation_revision_and_provider_matrix(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment = _create_sample(harness.client)
    assignment_id = assignment["assignment_id"]
    question_id = assignment["questions"][0]["question_id"]
    version = assignment["version"]

    _assert_error(
        harness.client.post(
            f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
            json={
                "assignment_version": version,
                "candidate_id": "cand_missing",
                "candidate_version": 1,
            },
            headers=MUTATION_HEADERS,
        ),
        409,
        "candidate_not_found",
    )
    _assert_error(
        harness.client.patch(
            f"/api/v2/assignments/{assignment_id}/questions/{question_id}/answer",
            json={"assignment_version": version},
            headers=MUTATION_HEADERS,
        ),
        409,
        "candidate_not_found",
    )

    interactions = [
        (
            "Typed verbatim.",
            "student_verbatim",
            {"kind": "direct_typed"},
        ),
        (
            "Spoken verbatim.",
            "student_verbatim",
            {
                "kind": "direct_voice",
                "realtime_session_id": "rt_direct_one",
                "source_turn_ids": ["turn_1"],
                "normalization": "none",
            },
        ),
        (
            "Spoken, with punctuation.",
            "student_normalized",
            {
                "kind": "direct_voice",
                "realtime_session_id": "rt_direct_two",
                "source_turn_ids": ["turn_2"],
                "normalization": "punctuation_only",
            },
        ),
        (
            "My answer after thinking it through.",
            "student_after_guidance",
            {
                "kind": "guided_final",
                "realtime_session_id": "rt_guided",
                "source_turn_ids": ["turn_3", "turn_4"],
                "input": "typed",
            },
        ),
    ]
    current: dict[str, Any] | None = None
    for text, origin, interaction in interactions:
        payload = _post_candidate(
            harness.client,
            assignment_id=assignment_id,
            question_id=question_id,
            version=version,
            text=text,
            origin=origin,
            interaction=interaction,
        )
        assert payload["candidate"]["origin"] == origin
        version = payload["version"]
        current = payload["candidate"]

    assert current is not None
    edited = _post_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        version=version,
        text="My edited answer.",
        origin="student_edited",
        interaction={
            "kind": "student_edit",
            "prior_candidate_id": current["candidate_id"],
            "prior_candidate_version": current["candidate_version"],
        },
    )
    version = edited["version"]
    current = edited["candidate"]

    observed = harness.service.manifests.load(assignment_id)
    persisted_question = observed.manifest.questions[0]
    record = RephraseRecord(
        rephrase_id="rph_matrix",
        original_candidate_id=current["candidate_id"],
        original_candidate_version=current["candidate_version"],
        suggestion_candidate_id="cand_suggestion",
        suggestion_candidate_version=current["candidate_version"] + 1,
        suggestion_text="Plants turn sunlight into stored chemical energy.",
        factual_delta_safe=True,
    )
    persisted_question = persisted_question.model_copy(
        update={"rephrases": (*persisted_question.rephrases, record)}
    )
    harness.service.manifests.compare_and_swap(
        observed,
        observed.manifest.model_copy(
            update={"questions": (persisted_question, *observed.manifest.questions[1:])}
        ),
    )
    selected = _post_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        version=version,
        text=record.suggestion_text,
        origin="claros_rephrase",
        interaction={
            "kind": "selected_rephrase",
            "rephrase_id": record.rephrase_id,
            "suggestion_candidate_id": record.suggestion_candidate_id,
        },
    )
    assert selected["candidate"]["attribution"] == "Suggested wording"
    version = selected["version"]
    current = selected["candidate"]

    forged = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        json={
            "assignment_version": version,
            "text": "Forged suggestion.",
            "origin": "claros_rephrase",
            "interaction": {"kind": "direct_typed"},
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(forged, 422, "invalid_candidate_origin")

    stale = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        json={
            "assignment_version": version - 1,
            "text": "Stale answer.",
            "origin": "student_verbatim",
            "interaction": {"kind": "direct_typed"},
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(stale, 409, "assignment_version_conflict")
    assert stale.json()["version"] == version

    _assert_error(
        harness.client.post(
            f"/api/v2/assignments/{assignment_id}/questions/q_missing/candidates",
            json={
                "assignment_version": version,
                "text": "Missing question.",
                "origin": "student_verbatim",
                "interaction": {"kind": "direct_typed"},
            },
            headers=MUTATION_HEADERS,
        ),
        404,
        "question_not_found",
    )

    _assert_error(
        harness.client.post(
            f"/api/v2/assignments/{assignment_id}/questions/{question_id}/rephrase",
            json={
                "assignment_version": version,
                "candidate_id": current["candidate_id"],
                "candidate_version": current["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        ),
        503,
        "provider_unavailable",
    )
    stale_rephrase = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/rephrase",
        json={
            "assignment_version": version - 1,
            "candidate_id": current["candidate_id"],
            "candidate_version": current["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(stale_rephrase, 409, "assignment_version_conflict")
    _assert_error(
        harness.client.post(
            f"/api/v2/assignments/{assignment_id}/questions/q_missing/rephrase",
            json={
                "assignment_version": version,
                "candidate_id": current["candidate_id"],
                "candidate_version": current["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        ),
        404,
        "question_not_found",
    )
    _assert_error(
        harness.client.post(
            f"/api/v2/assignments/{assignment_id}/questions/{question_id}/rephrase",
            json={
                "assignment_version": version,
                "candidate_id": "cand_stale",
                "candidate_version": current["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        ),
        409,
        "candidate_not_found",
    )
    realtime_body = {
        "assignment_id": assignment_id,
        "assignment_version": version,
        "question_id": question_id,
        "mode": "direct",
    }
    realtime = harness.client.post(
        "/api/v2/realtime/client-secret",
        json=realtime_body,
        headers=MUTATION_HEADERS,
    )
    _assert_error(realtime, 503, "provider_unavailable")
    assert realtime.headers["etag"] == f'"assignment-version-{version}"'
    _assert_error(
        harness.client.post(
            "/api/v2/realtime/client-secret",
            json={**realtime_body, "assignment_version": version - 1},
            headers=MUTATION_HEADERS,
        ),
        409,
        "assignment_version_conflict",
    )
    _assert_error(
        harness.client.post(
            "/api/v2/realtime/client-secret",
            json={**realtime_body, "question_id": "q_missing"},
            headers=MUTATION_HEADERS,
        ),
        404,
        "question_not_found",
    )

    wrong_review = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        json={
            "assignment_version": version,
            "candidate_id": "cand_wrong",
            "candidate_version": current["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(wrong_review, 409, "candidate_not_found")

    stale_review = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        json={
            "assignment_version": version - 1,
            "candidate_id": current["candidate_id"],
            "candidate_version": current["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(stale_review, 409, "assignment_version_conflict")

    review = _review_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        version=version,
        candidate=current,
    )
    invalid_token = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": review["version"],
            "review_token": "x" * 32,
            "candidate_id": current["candidate_id"],
            "candidate_version": current["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(invalid_token, 409, "invalid_review")

    persisted = harness.service.manifests.load(assignment_id).manifest
    reviewed_hash = persisted.questions[0].review_tokens[-1].placement_hash
    changed_hash = ("0" if reviewed_hash != "0" * 64 else "1") * 64
    with monkeypatch.context() as scoped:
        scoped.setattr(
            service_module,
            "_canonical_review_plan",
            lambda *_args, **_kwargs: SimpleNamespace(
                outcome=review["placement"], placement_hash=changed_hash
            ),
        )
        changed = harness.client.post(
            f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
            json={
                "assignment_version": review["version"],
                "review_token": review["review_token"],
                "candidate_id": current["candidate_id"],
                "candidate_version": current["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        )
    _assert_error(changed, 409, "placement_changed")

    confirmation = _confirm_review(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        review=review,
    )
    assert confirmation["replayed"] is False

    altered_replay = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": review["version"],
            "review_token": review["review_token"],
            "candidate_id": "cand_altered",
            "candidate_version": current["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(altered_replay, 409, "stale_review")

    revision = harness.client.patch(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/answer",
        json={"assignment_version": confirmation["version"]},
        headers=MUTATION_HEADERS,
    )
    assert revision.status_code == 200, revision.text
    revision_payload = revision.json()
    assert revision_payload["edit_seed"] == record.suggestion_text
    assert revision_payload["prior_confirmed_answer"]["revision"] == 1

    _assert_error(
        harness.client.patch(
            f"/api/v2/assignments/{assignment_id}/questions/{question_id}/answer",
            json={"assignment_version": confirmation["version"]},
            headers=MUTATION_HEADERS,
        ),
        409,
        "assignment_version_conflict",
    )

    revised_candidate = _post_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        version=revision_payload["version"],
        text="A revised exact answer.",
        origin="student_edited",
        interaction={
            "kind": "student_edit",
            "prior_candidate_id": current["candidate_id"],
            "prior_candidate_version": current["candidate_version"],
        },
    )
    stale_token_review = _review_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        version=revised_candidate["version"],
        candidate=revised_candidate["candidate"],
    )
    replacement = _post_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        version=stale_token_review["version"],
        text="Replacement after review.",
        origin="student_verbatim",
        interaction={"kind": "direct_typed"},
    )
    _assert_error(
        harness.client.post(
            f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
            json={
                "assignment_version": stale_token_review["version"],
                "review_token": stale_token_review["review_token"],
                "candidate_id": stale_token_review["candidate"]["candidate_id"],
                "candidate_version": stale_token_review["candidate"]["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        ),
        409,
        "stale_review",
    )

    expiring_review = _review_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question_id,
        version=replacement["version"],
        candidate=replacement["candidate"],
    )
    harness.clock.advance(seconds=harness.settings.review_ttl_seconds + 1)
    expired = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": expiring_review["version"],
            "review_token": expiring_review["review_token"],
            "candidate_id": expiring_review["candidate"]["candidate_id"],
            "candidate_version": expiring_review["candidate"]["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    _assert_error(expired, 409, "review_expired")


def test_export_status_context_and_download_matrix(harness: Harness) -> None:
    assignment, confirmation = _answer_first_question(harness)
    assignment_id = assignment["assignment_id"]
    question = assignment["questions"][0]
    created = harness.client.post(
        f"/api/v2/assignments/{assignment_id}/exports",
        json={
            "assignment_version": confirmation["version"],
            "idempotency_key": "matrix-complete-export-0001",
        },
        headers=MUTATION_HEADERS,
    )
    assert created.status_code == 201, created.text
    export = created.json()
    assert export["status"] == "complete"

    status = harness.client.get(
        f"/api/v2/assignments/{assignment_id}/exports/{export['export_id']}"
    )
    assert status.status_code == 200, status.text
    assert status.json() == export
    assert status.headers["etag"] == f'"assignment-version-{export["version"]}"'

    confirmed_context = harness.client.get(
        f"/api/v2/assignments/{assignment_id}/pages/{question['page_number']}/context",
        params={"question_id": question["question_id"], "preview": "confirmed"},
    )
    assert confirmed_context.status_code == 200, confirmed_context.text
    assert confirmed_context.json()["source_status"] == "completed_copy_preview"
    assert confirmed_context.json()["source_url"] == export["download_url"]

    full = harness.client.get(export["download_url"])
    assert full.status_code == 200
    assert full.content.startswith(b"%PDF-")
    assert full.headers["content-disposition"].startswith("attachment;")

    full_head = harness.client.head(export["download_url"])
    assert full_head.status_code == 200
    assert full_head.content == b""
    assert int(full_head.headers["content-length"]) == len(full.content)

    ranged = harness.client.get(export["download_url"], headers={"Range": "bytes=0-15"})
    assert ranged.status_code == 206
    assert ranged.content == full.content[:16]
    assert ranged.headers["content-range"].startswith("bytes 0-15/")

    ranged_head = harness.client.head(export["download_url"], headers={"Range": "bytes=0-15"})
    assert ranged_head.status_code == 206
    assert ranged_head.content == b""
    assert ranged_head.headers["content-length"] == "16"

    _assert_error(
        harness.client.get(export["download_url"], headers={"Range": "bytes=999999999-"}),
        416,
        "range_not_satisfiable",
    )
    _assert_error(
        harness.client.get(f"/api/v2/assignments/{assignment_id}/exports/exp_missing"),
        404,
        "export_not_found",
    )
    _assert_error(
        harness.client.get(f"/api/v2/assignments/{assignment_id}/exports/exp_missing/download"),
        404,
        "export_not_found",
    )

    manifest = harness.service.manifests.load(assignment_id).manifest
    completed = manifest.exports[0]
    assert completed.object_ref is not None
    harness.store.delete(
        completed.object_ref.key,
        expected_generation=completed.object_ref.generation,
    )
    _assert_error(harness.client.get(export["download_url"]), 409, "invalid_export")


def test_export_failure_polling_and_error_translation(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment = _create_sample(harness.client)
    assignment_id = assignment["assignment_id"]
    _assert_error(
        harness.client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": assignment["version"],
                "idempotency_key": "matrix-no-answer-export-0001",
            },
            headers=MUTATION_HEADERS,
        ),
        409,
        "no_confirmed_answers",
    )

    question = assignment["questions"][0]
    candidate_payload = _post_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question["question_id"],
        version=assignment["version"],
        text="An answer used to exercise export failures.",
        origin="student_verbatim",
        interaction={"kind": "direct_typed"},
    )
    review = _review_candidate(
        harness.client,
        assignment_id=assignment_id,
        question_id=question["question_id"],
        version=candidate_payload["version"],
        candidate=candidate_payload["candidate"],
    )
    confirmation = _confirm_review(
        harness.client,
        assignment_id=assignment_id,
        question_id=question["question_id"],
        review=review,
    )

    async def export_timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise DocumentExecutionTimeout

    with monkeypatch.context() as scoped:
        scoped.setattr(harness.service.document_executor, "export", export_timeout)
        timed_out = harness.client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": confirmation["version"],
                "idempotency_key": "matrix-timeout-export-0001",
            },
            headers=MUTATION_HEADERS,
        )
    _assert_error(timed_out, 503, "export_timeout")

    manifest = harness.service.manifests.load(assignment_id).manifest
    export_id = manifest.exports[0].export_id
    failed_status = harness.client.get(f"/api/v2/assignments/{assignment_id}/exports/{export_id}")
    assert failed_status.status_code == 200, failed_status.text
    assert failed_status.json()["status"] == "failed"
    assert failed_status.json()["failure"]["code"] == "publish_failed"
    assert failed_status.json()["download_url"] is None
    _assert_error(
        harness.client.get(f"/api/v2/assignments/{assignment_id}/exports/{export_id}/download"),
        409,
        "export_not_ready",
    )

    async def export_crash(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("private renderer detail")

    with monkeypatch.context() as scoped:
        scoped.setattr(harness.service.document_executor, "export", export_crash)
        crashed = harness.client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": confirmation["version"],
                "idempotency_key": "matrix-crash-export-0001",
            },
            headers=MUTATION_HEADERS,
        )
    _assert_error(crashed, 503, "publish_failed")
    assert "private renderer detail" not in crashed.text

    async def unsupported_glyph(*_args: Any, **_kwargs: Any) -> Any:
        raise DocumentEngineError(
            "unsupported_glyph",
            "This answer contains a character the PDF font cannot render safely.",
        )

    with monkeypatch.context() as scoped:
        scoped.setattr(harness.service.document_executor, "export", unsupported_glyph)
        unsupported = harness.client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": confirmation["version"],
                "idempotency_key": "matrix-glyph-export-0001",
            },
            headers=MUTATION_HEADERS,
        )
    _assert_error(unsupported, 422, "unsupported_glyph")
    final_status = harness.client.get(f"/api/v2/assignments/{assignment_id}/exports/{export_id}")
    assert final_status.json()["failure"]["code"] == "unsupported_glyph"


def test_provider_success_route_contracts_are_adapter_ready(tmp_path: Path) -> None:
    original = Candidate(
        candidate_id="cand_original",
        candidate_version=1,
        question_id="q_1",
        text="My words.",
        origin=CandidateOrigin.STUDENT_VERBATIM,
        attribution=StudentAttribution.YOUR_WORDS,
        created_at=NOW,
    )
    suggestion = Candidate(
        candidate_id="cand_suggestion",
        candidate_version=2,
        question_id="q_1",
        text="Suggested wording.",
        origin=CandidateOrigin.CLAROS_REPHRASE,
        attribution=StudentAttribution.SUGGESTED_WORDING,
        created_at=NOW,
    )

    class ProviderStub:
        async def request_rephrase(self, **_kwargs: Any) -> RephraseResponse:
            return RephraseResponse(
                version=7,
                rephrase_id="rph_route",
                original=original,
                suggestion=suggestion,
                selected_candidate_id=None,
                factual_delta_safe=True,
            )

        async def issue_realtime_credential(self, **_kwargs: Any) -> RealtimeCredentialResponse:
            return RealtimeCredentialResponse(
                version=7,
                session_id="rt_route",
                client_secret=EPHEMERAL_TEST_SECRET,
                expires_at=NOW + timedelta(minutes=1),
                model="gpt-realtime-test",
            )

    settings = _settings(tmp_path / "provider-route-objects")
    with TestClient(create_app(settings=settings, assignment_service=ProviderStub())) as client:
        rephrase = client.post(
            "/api/v2/assignments/asn_route/questions/q_1/rephrase",
            json={
                "assignment_version": 7,
                "candidate_id": "cand_original",
                "candidate_version": 1,
            },
            headers=MUTATION_HEADERS,
        )
        assert rephrase.status_code == 200, rephrase.text
        assert rephrase.headers["etag"] == '"assignment-version-7"'
        assert rephrase.json()["suggestion"]["attribution"] == "Suggested wording"

        realtime = client.post(
            "/api/v2/realtime/client-secret",
            json={
                "assignment_id": "asn_route",
                "assignment_version": 7,
                "question_id": "q_1",
                "mode": "guided",
            },
            headers=MUTATION_HEADERS,
        )
        assert realtime.status_code == 200, realtime.text
        assert realtime.headers["etag"] == '"assignment-version-7"'
        assert realtime.json()["client_secret"] == EPHEMERAL_TEST_SECRET
