from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.models import (
    MAX_CANDIDATE_UTF8_BYTES,
    AssignmentResponse,
    AssignmentStatus,
    CandidateOrigin,
    CandidateRequest,
    DirectTypedInteraction,
    PlacementSummary,
    SourceDocument,
)
from backend.config import Settings
from backend.main import create_app


def test_openapi_has_the_complete_unique_operation_inventory() -> None:
    schema = create_app(settings=Settings(environment="test")).openapi()
    operations = [
        operation["operationId"]
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in {"get", "head", "post", "patch"}
    ]

    assert set(operations) == {
        "health",
        "create_assignment",
        "get_assignment",
        "get_assignment_source",
        "head_assignment_source",
        "get_page_context",
        "create_candidate",
        "request_rephrase",
        "create_review",
        "confirm_answer",
        "begin_answer_revision",
        "create_export",
        "get_export",
        "download_export",
        "head_export",
        "issue_realtime_client_secret",
    }
    assert len(operations) == len(set(operations))


def test_assignment_creation_is_the_only_versionless_mutation() -> None:
    schema = create_app(settings=Settings(environment="test")).openapi()
    mutation_operations = {
        operation["operationId"]: operation
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in {"post", "patch"}
    }

    create_body = mutation_operations["create_assignment"]["requestBody"]
    assert "multipart/form-data" in create_body["content"]

    for operation_id, operation in mutation_operations.items():
        if operation_id == "create_assignment":
            continue
        request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        reference_name = request_schema["$ref"].rsplit("/", 1)[-1]
        required = schema["components"]["schemas"][reference_name]["required"]
        assert "assignment_version" in required, operation_id


def test_openapi_declares_etag_on_versioned_and_binary_success_responses() -> None:
    schema = create_app(settings=Settings(environment="test")).openapi()
    versioned = [
        ("/api/v2/assignments", "post", "201"),
        ("/api/v2/assignments/{assignment_id}", "get", "200"),
        (
            "/api/v2/assignments/{assignment_id}/pages/{page_number}/context",
            "get",
            "200",
        ),
        (
            "/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
            "post",
            "200",
        ),
        (
            "/api/v2/assignments/{assignment_id}/questions/{question_id}/rephrase",
            "post",
            "200",
        ),
        (
            "/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
            "post",
            "200",
        ),
        (
            "/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
            "post",
            "200",
        ),
        (
            "/api/v2/assignments/{assignment_id}/questions/{question_id}/answer",
            "patch",
            "200",
        ),
        ("/api/v2/assignments/{assignment_id}/exports", "post", "201"),
        ("/api/v2/assignments/{assignment_id}/exports", "post", "200"),
        (
            "/api/v2/assignments/{assignment_id}/exports/{export_id}",
            "get",
            "200",
        ),
        ("/api/v2/realtime/client-secret", "post", "200"),
    ]
    binary = [
        ("/api/v2/assignments/{assignment_id}/source", "get"),
        ("/api/v2/assignments/{assignment_id}/source", "head"),
        (
            "/api/v2/assignments/{assignment_id}/exports/{export_id}/download",
            "get",
        ),
        (
            "/api/v2/assignments/{assignment_id}/exports/{export_id}/download",
            "head",
        ),
    ]

    for path, method, response_status in versioned:
        assert "ETag" in schema["paths"][path][method]["responses"][response_status]["headers"]
    for path, method in binary:
        responses = schema["paths"][path][method]["responses"]
        assert "ETag" in responses["200"]["headers"]
        assert "ETag" in responses["206"]["headers"]


def test_candidate_validation_preserves_exact_unicode_and_whitespace() -> None:
    exact = "  José’s café — 植物\nsecond line  "  # noqa: RUF001 - exact Unicode fixture
    request = CandidateRequest(
        assignment_version=1,
        text=exact,
        origin=CandidateOrigin.STUDENT_VERBATIM,
        interaction=DirectTypedInteraction(kind="direct_typed"),
    )

    assert request.text == exact


@pytest.mark.parametrize("text", ["", "   \n\t", "contains\x00nul"])
def test_candidate_validation_rejects_empty_or_nul_text(text: str) -> None:
    with pytest.raises(ValidationError):
        CandidateRequest(
            assignment_version=1,
            text=text,
            origin=CandidateOrigin.STUDENT_VERBATIM,
            interaction=DirectTypedInteraction(kind="direct_typed"),
        )


def test_candidate_limit_is_utf8_bytes_without_rewriting_text() -> None:
    accepted = "é" * (MAX_CANDIDATE_UTF8_BYTES // 2)
    assert (
        CandidateRequest(
            assignment_version=1,
            text=accepted,
            origin=CandidateOrigin.STUDENT_VERBATIM,
            interaction=DirectTypedInteraction(kind="direct_typed"),
        ).text
        == accepted
    )

    with pytest.raises(ValidationError):
        CandidateRequest(
            assignment_version=1,
            text=accepted + "é",
            origin=CandidateOrigin.STUDENT_VERBATIM,
            interaction=DirectTypedInteraction(kind="direct_typed"),
        )


def test_validation_errors_use_only_the_stable_envelope() -> None:
    app = create_app(settings=Settings(environment="test"))
    client = TestClient(app)

    response = client.post(
        "/api/v2/assignments/a/questions/q/candidates",
        json={"assignment_version": "1", "text": "private answer"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "The request could not be accepted. Check it and try again.",
            "recoverable": True,
        }
    }
    assert "private answer" not in response.text


class AssignmentStub:
    async def get_assignment(self, **_kwargs: object) -> AssignmentResponse:
        return AssignmentResponse(
            assignment_id="assignment_01",
            version=7,
            status=AssignmentStatus.READY,
            title="Biology",
            source=SourceDocument(
                filename="biology.pdf",
                size_bytes=1024,
                sha256="a" * 64,
                page_count=1,
            ),
            question_count=0,
            placement_summary=PlacementSummary(inline_possible=0, appendix_only=0),
            warnings=[],
            questions=[],
        )


def test_json_state_response_returns_the_frozen_etag() -> None:
    app = create_app(
        settings=Settings(environment="test"),
        assignment_service=AssignmentStub(),
    )
    response = TestClient(app).get("/api/v2/assignments/assignment_01")

    assert response.status_code == 200
    assert response.headers["etag"] == '"assignment-version-7"'
    assert response.json()["version"] == 7


def test_health_is_small_and_does_not_require_storage() -> None:
    response = TestClient(create_app(settings=Settings(environment="test"))).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_configuration_rejects_local_storage_and_default_secrets() -> None:
    with pytest.raises(ValidationError, match="production requires GCS storage"):
        Settings(environment="production", storage_backend="local")

    with pytest.raises(ValidationError, match="cookie secret must be at least 32 UTF-8 bytes"):
        Settings(
            environment="production",
            storage_backend="gcs",
            gcs_bucket="private-bucket",
            public_origin="https://claros.example",
        )


def test_transport_models_emit_utc_datetimes() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    payload = SourceDocument(
        filename="worksheet.pdf",
        size_bytes=1,
        sha256="f" * 64,
        page_count=1,
    ).model_dump(mode="json")

    assert payload["filename"] == "worksheet.pdf"
    assert now.isoformat() == "2026-09-04T00:00:00+00:00"
