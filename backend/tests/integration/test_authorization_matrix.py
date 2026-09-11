"""Cross-owner authorization coverage for every Gate 3 assignment boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.models import (
    AssignmentResponse,
    AssignmentStatus,
    PlacementSummary,
    SourceDocument,
)
from backend.config import Settings
from backend.main import create_app
from backend.security import create_owner_session

ORIGIN = "http://testserver"
MUTATION_HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
OWNER_TEST_SECRET = "authorization-owner-secret-with-sufficient-entropy"  # noqa: S105
REVIEW_TEST_SECRET = "authorization-review-secret-with-sufficient-entropy"  # noqa: S105
SAFE_DENIAL = {
    "error": {
        "code": "assignment_not_found",
        "message": "This worksheet session is no longer available.",
        "recoverable": False,
    }
}


@dataclass(frozen=True, slots=True)
class BoundaryRequest:
    name: str
    method: str
    path: str
    payload: dict[str, object] | None = None
    headers: dict[str, str] | None = None


def _settings(storage_root: Path) -> Settings:
    return Settings(
        environment="test",
        storage_backend="local",
        local_storage_path=storage_root,
        public_origin=ORIGIN,
        cookie_secret=OWNER_TEST_SECRET,
        review_token_secret=REVIEW_TEST_SECRET,
    )


def _create_completed_assignment(client: TestClient) -> dict[str, object]:
    created_response = client.post(
        "/api/v2/assignments",
        data={"sample_id": "biology-short-answer"},
        headers=MUTATION_HEADERS,
    )
    assert created_response.status_code == 201, created_response.text
    assignment = created_response.json()
    assignment_id = assignment["assignment_id"]
    question_id = assignment["questions"][0]["question_id"]

    candidate_response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        json={
            "assignment_version": assignment["version"],
            "text": "Plants use sunlight to make glucose.",
            "origin": "student_verbatim",
            "interaction": {"kind": "direct_typed"},
        },
        headers=MUTATION_HEADERS,
    )
    assert candidate_response.status_code == 200, candidate_response.text
    candidate_payload = candidate_response.json()
    candidate = candidate_payload["candidate"]

    review_response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        json={
            "assignment_version": candidate_payload["version"],
            "candidate_id": candidate["candidate_id"],
            "candidate_version": candidate["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    assert review_response.status_code == 200, review_response.text
    review = review_response.json()

    confirm_response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": review["version"],
            "review_token": review["review_token"],
            "candidate_id": candidate["candidate_id"],
            "candidate_version": candidate["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirmation = confirm_response.json()

    export_response = client.post(
        f"/api/v2/assignments/{assignment_id}/exports",
        json={
            "assignment_version": confirmation["version"],
            "idempotency_key": "authorization-matrix-export-0001",
        },
        headers=MUTATION_HEADERS,
    )
    assert export_response.status_code == 201, export_response.text
    export = export_response.json()
    assert export["status"] == "complete"

    current_response = client.get(f"/api/v2/assignments/{assignment_id}")
    assert current_response.status_code == 200, current_response.text
    current = current_response.json()
    return {
        "assignment_id": assignment_id,
        "candidate": candidate,
        "current_version": current["version"],
        "export_id": export["export_id"],
        "question_id": question_id,
        "review": review,
    }


def _boundary_requests(state: dict[str, object]) -> tuple[BoundaryRequest, ...]:
    assignment_id = state["assignment_id"]
    question_id = state["question_id"]
    export_id = state["export_id"]
    current_version = state["current_version"]
    candidate = state["candidate"]
    review = state["review"]
    assert isinstance(candidate, dict)
    assert isinstance(review, dict)

    assignment_path = f"/api/v2/assignments/{assignment_id}"
    question_path = f"{assignment_path}/questions/{question_id}"
    download_path = f"{assignment_path}/exports/{export_id}/download"
    return (
        BoundaryRequest("assignment status", "GET", assignment_path),
        BoundaryRequest("source GET", "GET", f"{assignment_path}/source"),
        BoundaryRequest("source HEAD", "HEAD", f"{assignment_path}/source"),
        BoundaryRequest(
            "source Range",
            "GET",
            f"{assignment_path}/source",
            headers={"Range": "bytes=0-31"},
        ),
        BoundaryRequest(
            "page context",
            "GET",
            f"{assignment_path}/pages/1/context?question_id={question_id}&preview=original",
        ),
        BoundaryRequest(
            "candidate",
            "POST",
            f"{question_path}/candidates",
            payload={
                "assignment_version": current_version,
                "text": "A syntactically valid unauthorized candidate.",
                "origin": "student_verbatim",
                "interaction": {"kind": "direct_typed"},
            },
            headers=MUTATION_HEADERS,
        ),
        BoundaryRequest(
            "rephrase",
            "POST",
            f"{question_path}/rephrase",
            payload={
                "assignment_version": current_version,
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        ),
        BoundaryRequest(
            "review",
            "POST",
            f"{question_path}/review",
            payload={
                "assignment_version": current_version,
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        ),
        BoundaryRequest(
            "confirm",
            "POST",
            f"{question_path}/confirm",
            payload={
                "assignment_version": review["version"],
                "review_token": review["review_token"],
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        ),
        BoundaryRequest(
            "revision",
            "PATCH",
            f"{question_path}/answer",
            payload={"assignment_version": current_version},
            headers=MUTATION_HEADERS,
        ),
        BoundaryRequest(
            "export create",
            "POST",
            f"{assignment_path}/exports",
            payload={
                "assignment_version": current_version,
                "idempotency_key": "authorization-matrix-denied-0001",
            },
            headers=MUTATION_HEADERS,
        ),
        BoundaryRequest("export status", "GET", f"{assignment_path}/exports/{export_id}"),
        BoundaryRequest("export download GET", "GET", download_path),
        BoundaryRequest("export download HEAD", "HEAD", download_path),
        BoundaryRequest(
            "Realtime credential",
            "POST",
            "/api/v2/realtime/client-secret",
            payload={
                "assignment_id": assignment_id,
                "assignment_version": current_version,
                "question_id": question_id,
                "mode": "direct",
            },
            headers=MUTATION_HEADERS,
        ),
    )


def test_all_assignment_boundaries_deny_cross_owner_missing_and_invalid_sessions(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "objects")
    app = create_app(settings=settings)

    with TestClient(app) as owner:
        state = _create_completed_assignment(owner)
        owner_cookie = owner.cookies.get(settings.owner_cookie_name)
        assert owner_cookie is not None

        origin_blocked = owner.patch(
            (
                f"/api/v2/assignments/{state['assignment_id']}"
                f"/questions/{state['question_id']}/answer"
            ),
            json={"assignment_version": state["current_version"]},
        )
        assert origin_blocked.status_code == 403
        assert origin_blocked.json()["error"]["code"] == "origin_forbidden"

    _session, cross_owner_cookie = create_owner_session(
        OWNER_TEST_SECRET,
        owner_id_factory=lambda: "own_authorization_matrix_b",
    )
    assert cross_owner_cookie != owner_cookie

    cookie_cases = (
        ("cross-owner", cross_owner_cookie),
        ("missing", None),
        ("invalid", "invalid-owner-session"),
    )
    requests = _boundary_requests(state)
    assert len(requests) == 15

    for cookie_case, cookie in cookie_cases:
        with TestClient(app) as unauthorized:
            if cookie is not None:
                unauthorized.cookies.set(settings.owner_cookie_name, cookie)

            for boundary in requests:
                request_arguments: dict[str, object] = {}
                if boundary.payload is not None:
                    request_arguments["json"] = boundary.payload
                if boundary.headers is not None:
                    request_arguments["headers"] = boundary.headers
                response = unauthorized.request(
                    boundary.method,
                    boundary.path,
                    **request_arguments,
                )

                assertion_context = f"{cookie_case}: {boundary.name}: {response.text}"
                assert response.status_code == 404, assertion_context
                assert response.headers["cache-control"] == "private, no-store"
                assert "etag" not in response.headers
                assert "content-range" not in response.headers
                if boundary.method == "HEAD":
                    assert response.content == b"", assertion_context
                else:
                    assert response.json() == SAFE_DENIAL, assertion_context


class _ProductionCreationStub:
    async def create_assignment(self, **kwargs: object) -> tuple[AssignmentResponse, str]:
        assert kwargs["sample_id"] == "biology-short-answer"
        assert kwargs["file"] is None
        return (
            AssignmentResponse(
                assignment_id="asn_production_cookie_flags",
                version=1,
                status=AssignmentStatus.ANALYZING,
                title="Production cookie fixture",
                source=SourceDocument(
                    filename="worksheet.pdf",
                    size_bytes=1,
                    sha256="0" * 64,
                    page_count=None,
                ),
                question_count=0,
                placement_summary=PlacementSummary(inline_possible=0, appendix_only=0),
            ),
            "stub-signed-owner-session",
        )


def test_production_assignment_creation_sets_required_owner_cookie_attributes() -> None:
    production_origin = "https://claros.example"
    settings = Settings(
        environment="production",
        storage_backend="gcs",
        gcs_bucket="private-claros-fixtures",
        public_origin=production_origin,
        cookie_secret=OWNER_TEST_SECRET,
        review_token_secret=REVIEW_TEST_SECRET,
    )
    app = create_app(settings=settings, assignment_service=_ProductionCreationStub())

    with TestClient(app, base_url=production_origin) as client:
        response = client.post(
            "/api/v2/assignments",
            data={"sample_id": "biology-short-answer"},
            headers={"Origin": production_origin, "Sec-Fetch-Site": "same-origin"},
        )

    assert response.status_code == 201, response.text
    cookie_attributes = {
        part.strip().casefold() for part in response.headers["set-cookie"].split(";")[1:]
    }
    assert {"secure", "httponly", "samesite=lax"} <= cookie_attributes
