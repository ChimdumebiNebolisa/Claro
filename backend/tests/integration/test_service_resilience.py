"""Exercise durable recovery and fail-closed service boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.domain import ExportStatus as DomainExportStatus
from backend.domain import start_export
from backend.main import create_app
from backend.security import verify_owner_session
from backend.service import AssignmentApplicationService
from backend.storage import LocalObjectStore, assignment_manifest_object_key

ORIGIN = "http://testserver"
MUTATION_HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}


@dataclass
class MutableClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _settings(storage_root: Path, *, assignment_ttl_seconds: int = 86_400) -> Settings:
    return Settings(
        environment="test",
        storage_backend="local",
        local_storage_path=storage_root,
        public_origin=ORIGIN,
        cookie_secret="resilience-owner-secret-with-sufficient-entropy",  # noqa: S106
        review_token_secret="resilience-review-secret-with-sufficient-entropy",  # noqa: S106
        assignment_ttl_seconds=assignment_ttl_seconds,
    )


def _harness(
    tmp_path: Path,
    *,
    clock: MutableClock | None = None,
    assignment_ttl_seconds: int = 86_400,
) -> tuple[Settings, LocalObjectStore, AssignmentApplicationService, TestClient]:
    settings = _settings(
        tmp_path / "objects",
        assignment_ttl_seconds=assignment_ttl_seconds,
    )
    store = LocalObjectStore(settings.local_storage_path)
    service = AssignmentApplicationService(
        settings=settings,
        store=store,
        now=clock or MutableClock(datetime(2040, 1, 1, tzinfo=UTC)),
    )
    client = TestClient(create_app(settings=settings, assignment_service=service))
    return settings, store, service, client


def _create_sample(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v2/assignments",
        data={"sample_id": "biology-short-answer"},
        headers=MUTATION_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm_question(
    client: TestClient,
    *,
    assignment_id: str,
    question_id: str,
    assignment_version: int,
    exact_text: str,
) -> dict[str, Any]:
    candidate_response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        json={
            "assignment_version": assignment_version,
            "text": exact_text,
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

    confirmation_response = client.post(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        json={
            "assignment_version": review["version"],
            "review_token": review["review_token"],
            "candidate_id": review["candidate"]["candidate_id"],
            "candidate_version": review["candidate"]["candidate_version"],
        },
        headers=MUTATION_HEADERS,
    )
    assert confirmation_response.status_code == 200, confirmation_response.text
    return confirmation_response.json()


def _create_confirmed_assignment(
    client: TestClient,
) -> tuple[dict[str, Any], dict[str, Any]]:
    assignment = _create_sample(client)
    question = assignment["questions"][0]
    confirmation = _confirm_question(
        client,
        assignment_id=assignment["assignment_id"],
        question_id=question["question_id"],
        assignment_version=assignment["version"],
        exact_text="Plants use sunlight to make glucose.",
    )
    return assignment, confirmation


def _corrupt_local_object(store: LocalObjectStore, key: str) -> None:
    target = store.root.joinpath(*key.split("/"))
    payload = bytearray(target.read_bytes())
    assert payload
    payload[-1] ^= 0x01
    target.write_bytes(payload)


def test_abandoned_export_lease_is_recovered_after_timeout(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2040, 1, 1, tzinfo=UTC))
    settings, _store, service, client = _harness(tmp_path, clock=clock)
    with client:
        assignment, confirmation = _create_confirmed_assignment(client)
        assignment_id = assignment["assignment_id"]
        observed = service.manifests.load(assignment_id)
        abandoned = start_export(
            observed.manifest,
            assignment_version=confirmation["version"],
            idempotency_key="abandoned-export-key-0001",
            now=clock(),
            stale_after_seconds=settings.request_timeout_seconds,
        )
        service.manifests.compare_and_swap(observed, abandoned.manifest)

        clock.advance(seconds=settings.request_timeout_seconds + 1)
        recovered_response = client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": confirmation["version"],
                "idempotency_key": "replacement-export-key-0001",
            },
            headers=MUTATION_HEADERS,
        )

        assert recovered_response.status_code == 200, recovered_response.text
        recovered = recovered_response.json()
        assert recovered["export_id"] == abandoned.export.export_id
        assert recovered["status"] == "complete"
        persisted = service.manifests.load(assignment_id)
        export = persisted.manifest.exports[0]
        assert export.status == DomainExportStatus.COMPLETE
        assert export.created_at == clock()


def test_concurrent_export_completion_reconciles_identical_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_value, _store, service, client = _harness(tmp_path)
    with client:
        assignment, confirmation = _create_confirmed_assignment(client)
        assignment_id = assignment["assignment_id"]
        original_save = service._save
        raced = False

        def save_with_competing_completion(observed: Any, updated: Any) -> Any:
            nonlocal raced
            is_completion = any(
                item.status == DomainExportStatus.COMPLETE for item in updated.exports
            )
            if is_completion and not raced:
                raced = True
                service.manifests.compare_and_swap(observed, updated)
            return original_save(observed, updated)

        monkeypatch.setattr(service, "_save", save_with_competing_completion)
        response = client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": confirmation["version"],
                "idempotency_key": "concurrent-export-key-0001",
            },
            headers=MUTATION_HEADERS,
        )

        assert raced is True
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "complete"
        persisted = service.manifests.load(assignment_id)
        assert len(persisted.manifest.exports) == 1
        assert persisted.manifest.exports[0].status == DomainExportStatus.COMPLETE


def test_reverse_confirmation_exports_in_source_order_and_preserves_physical_ir(
    tmp_path: Path,
) -> None:
    _settings_value, store, service, client = _harness(tmp_path)
    with client:
        assignment = _create_sample(client)
        assignment_id = assignment["assignment_id"]
        question_1, question_2 = assignment["questions"][:2]
        initial = service.manifests.load(assignment_id)
        assert initial.manifest.physical_ir is not None
        ir_reference = initial.manifest.physical_ir
        ir_before = store.read(ir_reference.key)

        confirmed_2 = _confirm_question(
            client,
            assignment_id=assignment_id,
            question_id=question_2["question_id"],
            assignment_version=assignment["version"],
            exact_text="Sunlight supplies the energy used to build glucose.",
        )
        confirmed_1 = _confirm_question(
            client,
            assignment_id=assignment_id,
            question_id=question_1["question_id"],
            assignment_version=confirmed_2["version"],
            exact_text="Plants need sunlight as the energy source for photosynthesis.",
        )
        export_response = client.post(
            f"/api/v2/assignments/{assignment_id}/exports",
            json={
                "assignment_version": confirmed_1["version"],
                "idempotency_key": "source-order-export-key-0001",
            },
            headers=MUTATION_HEADERS,
        )
        assert export_response.status_code == 201, export_response.text

        persisted = service.manifests.load(assignment_id)
        completed = persisted.manifest.exports[0]
        assert completed.manifest_ref is not None
        export_manifest = json.loads(store.read(completed.manifest_ref.key).data)
        assert [item["question_id"] for item in export_manifest["answers"]] == [
            question_1["question_id"],
            question_2["question_id"],
        ]
        assert [item["exact_text_sha256"] for item in export_manifest["answers"]] == [
            hashlib.sha256(
                b"Plants need sunlight as the energy source for photosynthesis."
            ).hexdigest(),
            hashlib.sha256(b"Sunlight supplies the energy used to build glucose.").hexdigest(),
        ]

        ir_after = store.read(ir_reference.key)
        assert ir_after.metadata == ir_before.metadata
        assert ir_after.data == ir_before.data
        assert persisted.manifest.physical_ir == ir_reference

        download = client.get(export_response.json()["download_url"])
        assert download.status_code == 200
        assert download.headers["cache-control"] == "private, no-store"

        assert completed.object_ref is not None
        _corrupt_local_object(store, completed.object_ref.key)
        corrupt_download = client.get(export_response.json()["download_url"])
        assert corrupt_download.status_code == 409
        assert corrupt_download.json()["error"] == {
            "code": "invalid_export",
            "message": "The completed PDF could not be validated safely.",
            "recoverable": True,
        }


def test_refreshed_owner_cookie_does_not_extend_prior_assignment_lifetime(
    tmp_path: Path,
) -> None:
    clock = MutableClock(datetime(2040, 1, 1, tzinfo=UTC))
    settings, _store, service, client = _harness(
        tmp_path,
        clock=clock,
        assignment_ttl_seconds=60,
    )
    secret = settings.cookie_secret.get_secret_value()
    with client:
        first = _create_sample(client)
        first_cookie = client.cookies.get(settings.owner_cookie_name)
        assert first_cookie is not None
        first_session = verify_owner_session(first_cookie, secret, now=clock())

        clock.advance(seconds=30)
        second = _create_sample(client)
        refreshed_cookie = client.cookies.get(settings.owner_cookie_name)
        assert refreshed_cookie is not None
        refreshed_session = verify_owner_session(refreshed_cookie, secret, now=clock())

        assert refreshed_session.owner_id == first_session.owner_id
        assert refreshed_session.expires_at == clock() + timedelta(seconds=60)
        assert service.manifests.load(first["assignment_id"]).manifest.expires_at == (
            first_session.expires_at
        )
        assert service.manifests.load(second["assignment_id"]).manifest.expires_at == (
            refreshed_session.expires_at
        )

        clock.advance(seconds=31)
        client.cookies.set(settings.owner_cookie_name, refreshed_cookie)
        expired = client.get(f"/api/v2/assignments/{first['assignment_id']}")
        active = client.get(f"/api/v2/assignments/{second['assignment_id']}")
        assert expired.status_code == 404
        assert expired.json()["error"]["code"] == "assignment_not_found"
        assert active.status_code == 200, active.text


def test_storage_corruption_maps_to_stable_non_disclosing_errors(tmp_path: Path) -> None:
    _settings_value, store, service, client = _harness(tmp_path)
    with client:
        ir_assignment = _create_sample(client)
        ir_manifest = service.manifests.load(ir_assignment["assignment_id"]).manifest
        assert ir_manifest.physical_ir is not None
        _corrupt_local_object(store, ir_manifest.physical_ir.key)
        ir_response = client.get(f"/api/v2/assignments/{ir_assignment['assignment_id']}")
        assert ir_response.status_code == 409
        assert ir_response.json()["error"] == {
            "code": "stale_physical_ir",
            "message": "The worksheet analysis changed. Review the answer again.",
            "recoverable": True,
        }

        source_assignment = _create_sample(client)
        source_manifest = service.manifests.load(source_assignment["assignment_id"]).manifest
        _corrupt_local_object(store, source_manifest.source.key)
        source_response = client.get(
            f"/api/v2/assignments/{source_assignment['assignment_id']}/source"
        )
        assert source_response.status_code == 409
        assert source_response.json()["error"] == {
            "code": "stale_source",
            "message": "The worksheet source changed. Review the answer again.",
            "recoverable": True,
        }

        manifest_assignment = _create_sample(client)
        _corrupt_local_object(
            store,
            assignment_manifest_object_key(manifest_assignment["assignment_id"]),
        )
        manifest_response = client.get(
            f"/api/v2/assignments/{manifest_assignment['assignment_id']}"
        )
        assert manifest_response.status_code == 404
        assert manifest_response.json()["error"] == {
            "code": "assignment_not_found",
            "message": "This worksheet session is no longer available.",
            "recoverable": False,
        }


def test_all_api_and_pdf_response_paths_disable_shared_caching(tmp_path: Path) -> None:
    _settings_value, _store, _service, client = _harness(tmp_path)
    with client:
        created_response = client.post(
            "/api/v2/assignments",
            data={"sample_id": "biology-short-answer"},
            headers=MUTATION_HEADERS,
        )
        assert created_response.status_code == 201
        assignment = created_response.json()
        assignment_id = assignment["assignment_id"]

        responses = [
            created_response,
            client.get(f"/api/v2/assignments/{assignment_id}"),
            client.get(f"/api/v2/assignments/{assignment_id}/source"),
            client.head(f"/api/v2/assignments/{assignment_id}/source"),
            client.get(
                f"/api/v2/assignments/{assignment_id}/source",
                headers={"Range": "bytes=0-31"},
            ),
            client.get(
                f"/api/v2/assignments/{assignment_id}/source",
                headers={"Range": "bytes=999999999-"},
            ),
            client.get("/api/v2/route-that-does-not-exist"),
        ]
        assert [response.status_code for response in responses] == [
            201,
            200,
            200,
            200,
            206,
            416,
            404,
        ]
        assert all(
            response.headers["cache-control"] == "private, no-store" for response in responses
        )
