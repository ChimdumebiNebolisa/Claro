"""Deadline and event-loop isolation at the application service boundary."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

import anyio
import httpx
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.document import PreflightLimits
from backend.document_execution import DocumentExecutionTimeout, DocumentProcessExecutor
from backend.main import create_app
from backend.security import owner_hash
from backend.service import AssignmentApplicationService
from backend.storage import LocalObjectStore, ObjectNotFound

ORIGIN = "http://testserver"
MUTATION_HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
OWNER_SECRET = "deadline-owner-secret-with-sufficient-entropy"  # noqa: S105
REVIEW_SECRET = "deadline-review-secret-with-sufficient-entropy"  # noqa: S105
SAMPLE_PDF = (
    Path(__file__).resolve().parents[3] / "public" / "fixtures" / "claros-biology-short-answer.pdf"
)


def _settings(storage_root: Path) -> Settings:
    return Settings(
        environment="test",
        storage_backend="local",
        local_storage_path=storage_root,
        public_origin=ORIGIN,
        cookie_secret=OWNER_SECRET,
        review_token_secret=REVIEW_SECRET,
    )


class SleepingMissingStore:
    """A synchronous provider double that exposes event-loop blocking."""

    def read(self, _key: str) -> NoReturn:
        time.sleep(0.4)
        raise ObjectNotFound("private provider detail")


class ProviderDeadlineStore(SleepingMissingStore):
    def read(self, _key: str) -> NoReturn:
        raise TimeoutError("private provider deadline detail")


class DelayedCreateStore:
    def __init__(self, delegate: LocalObjectStore, delay_seconds: float) -> None:
        self.delegate = delegate
        self.delay_seconds = delay_seconds

    def create(self, *args: Any, **kwargs: Any) -> Any:
        time.sleep(self.delay_seconds)
        return self.delegate.create(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


class BudgetCapturingExecutor:
    timeout_seconds: float | None = None

    async def analyze(self, *_args: Any, timeout_seconds: float, **_kwargs: Any) -> NoReturn:
        self.timeout_seconds = timeout_seconds
        raise DocumentExecutionTimeout


def test_analysis_deadline_kills_and_reaps_document_worker(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "objects")
    executor = DocumentProcessExecutor(
        worker_module="backend.tests.helpers.sleeping_document_worker"
    )
    service = AssignmentApplicationService(
        settings=settings,
        store=LocalObjectStore(settings.local_storage_path),
        document_executor=executor,
        document_timeout_seconds=0.15,
    )

    started = time.perf_counter()
    with TestClient(create_app(settings=settings, assignment_service=service)) as client:
        response = client.post(
            "/api/v2/assignments",
            data={"sample_id": "biology-short-answer"},
            headers=MUTATION_HEADERS,
        )
        assignment = response.json()
        restored = client.get(f"/api/v2/assignments/{assignment['assignment_id']}")
    elapsed = time.perf_counter() - started

    assert response.status_code == 201
    assert assignment["status"] == "analysis_failed"
    assert assignment["warnings"] == [
        {
            "code": "analysis_timeout",
            "message": "Worksheet checking took too long. Try again.",
        }
    ]
    assert response.headers["set-cookie"].startswith("claros_owner=")
    assert restored.status_code == 200
    assert restored.json()["status"] == "analysis_failed"
    assert elapsed < 1.5
    assert executor.active_process_count == 0
    assert executor.last_worker_returncode is not None
    persisted = service.manifests.load(assignment["assignment_id"]).manifest
    assert persisted.status.value == "analysis_failed"
    assert persisted.failure_code == "analysis_timeout"
    assert persisted.physical_ir is None
    assert service.store.read(persisted.source.key).metadata.sha256 == persisted.source.sha256


async def test_cancelled_request_also_kills_and_reaps_document_worker() -> None:
    executor = DocumentProcessExecutor(
        worker_module="backend.tests.helpers.sleeping_document_worker"
    )

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(
            partial(
                executor.analyze,
                b"%PDF-test",
                limits=PreflightLimits(),
                timeout_seconds=30,
            )
        )
        with anyio.fail_after(2):
            while executor.active_process_count == 0:
                await anyio.sleep(0.01)
        tasks.cancel_scope.cancel()

    assert executor.active_process_count == 0
    assert executor.last_worker_returncode is not None


def test_export_deadline_kills_worker_and_persists_failed_export(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "objects")
    store = LocalObjectStore(settings.local_storage_path)
    service = AssignmentApplicationService(settings=settings, store=store)

    with TestClient(create_app(settings=settings, assignment_service=service)) as client:
        assignment_response = client.post(
            "/api/v2/assignments",
            data={"sample_id": "biology-short-answer"},
            headers=MUTATION_HEADERS,
        )
        assert assignment_response.status_code == 201
        assignment = assignment_response.json()
        question = assignment["questions"][0]
        candidate_response = client.post(
            f"/api/v2/assignments/{assignment['assignment_id']}"
            f"/questions/{question['question_id']}/candidates",
            json={
                "assignment_version": assignment["version"],
                "text": "Plants use sunlight to make food.",
                "origin": "student_verbatim",
                "interaction": {"kind": "direct_typed"},
            },
            headers=MUTATION_HEADERS,
        )
        assert candidate_response.status_code == 200
        candidate_payload = candidate_response.json()
        candidate = candidate_payload["candidate"]
        review_response = client.post(
            f"/api/v2/assignments/{assignment['assignment_id']}"
            f"/questions/{question['question_id']}/review",
            json={
                "assignment_version": candidate_payload["version"],
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        )
        assert review_response.status_code == 200
        review = review_response.json()
        confirmation_response = client.post(
            f"/api/v2/assignments/{assignment['assignment_id']}"
            f"/questions/{question['question_id']}/confirm",
            json={
                "assignment_version": review["version"],
                "review_token": review["review_token"],
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["candidate_version"],
            },
            headers=MUTATION_HEADERS,
        )
        assert confirmation_response.status_code == 200
        confirmation = confirmation_response.json()

        executor = DocumentProcessExecutor(
            worker_module="backend.tests.helpers.sleeping_document_worker"
        )
        service.document_executor = executor
        service._document_timeout_seconds = 0.15
        started = time.perf_counter()
        export_response = client.post(
            f"/api/v2/assignments/{assignment['assignment_id']}/exports",
            json={
                "assignment_version": confirmation["version"],
                "idempotency_key": "deadline-export-key-0001",
            },
            headers=MUTATION_HEADERS,
        )
        elapsed = time.perf_counter() - started

    assert export_response.status_code == 503
    assert export_response.json()["error"]["code"] == "export_timeout"
    assert elapsed < 1.5
    assert executor.active_process_count == 0
    assert executor.last_worker_returncode is not None
    persisted = service.manifests.load(assignment["assignment_id"]).manifest
    assert persisted.exports[0].status.value == "failed"
    assert persisted.exports[0].failure_code == "publish_failed"


async def test_slow_store_does_not_block_health_and_maps_deadline_safely(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "objects")
    service = AssignmentApplicationService(
        settings=settings,
        store=SleepingMissingStore(),  # type: ignore[arg-type]
        storage_timeout_seconds=0.08,
    )
    transport = httpx.ASGITransport(app=create_app(settings=settings, assignment_service=service))

    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        slow_request = asyncio.create_task(client.get("/api/v2/assignments/asn_missing"))
        await asyncio.sleep(0.02)
        health_started = time.perf_counter()
        health = await client.get("/health")
        health_elapsed = time.perf_counter() - health_started
        timed_out = await slow_request

    assert health.status_code == 200
    assert health_elapsed < 0.1
    assert timed_out.status_code == 503
    assert timed_out.json()["error"] == {
        "code": "storage_timeout",
        "message": "Worksheet storage took too long. Try again.",
        "recoverable": True,
    }
    assert "private provider detail" not in timed_out.text


async def test_mutation_timeout_settles_before_the_request_can_return(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "objects")
    service = AssignmentApplicationService(
        settings=settings,
        store=LocalObjectStore(settings.local_storage_path),
        storage_timeout_seconds=0.02,
    )
    publication_key = "assignments/asn_late/exports/exp_late/completed.pdf"
    publication_count = 0

    def publish() -> Any:
        nonlocal publication_count
        time.sleep(0.1)
        publication_count += 1
        return service.store.create(publication_key, b"%PDF-late", content_type="application/pdf")

    started = time.perf_counter()
    result = await service._run_storage(publish, timeout_seconds=0.02, mutation=True)
    elapsed = time.perf_counter() - started

    assert result.key == publication_key
    assert service.store.read(publication_key).metadata == result
    assert publication_count == 1
    assert elapsed >= 0.08
    await anyio.sleep(0.12)
    assert publication_count == 1
    assert service.store.read(publication_key).metadata == result


def test_assignment_uses_one_composite_budget_and_preserves_failed_state(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "objects")
    executor = BudgetCapturingExecutor()
    service = AssignmentApplicationService(
        settings=settings,
        store=DelayedCreateStore(  # type: ignore[arg-type]
            LocalObjectStore(settings.local_storage_path),
            delay_seconds=0.1,
        ),
        document_executor=executor,  # type: ignore[arg-type]
        document_timeout_seconds=0.6,
        storage_timeout_seconds=0.6,
        request_timeout_seconds=0.6,
    )

    with TestClient(create_app(settings=settings, assignment_service=service)) as client:
        response = client.post(
            "/api/v2/assignments",
            data={"sample_id": "biology-short-answer"},
            headers=MUTATION_HEADERS,
        )
        payload = response.json()
        restored = client.get(f"/api/v2/assignments/{payload['assignment_id']}")

    assert response.status_code == 201
    assert payload["status"] == "analysis_failed"
    assert restored.status_code == 200
    assert restored.json()["status"] == "analysis_failed"
    assert executor.timeout_seconds is not None
    assert 0 < executor.timeout_seconds < 0.45


async def test_provider_deadline_maps_to_the_same_safe_storage_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "objects")
    service = AssignmentApplicationService(
        settings=settings,
        store=ProviderDeadlineStore(),  # type: ignore[arg-type]
        storage_timeout_seconds=1,
    )
    transport = httpx.ASGITransport(app=create_app(settings=settings, assignment_service=service))

    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        response = await client.get("/api/v2/assignments/asn_missing")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_timeout"
    assert "private provider deadline detail" not in response.text


async def test_analyzing_projection_is_truthful_and_stale_analysis_recovers(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "objects")
    now = datetime(2040, 1, 1, tzinfo=UTC)
    store = LocalObjectStore(settings.local_storage_path)
    service = AssignmentApplicationService(
        settings=settings,
        store=store,
        now=lambda: now,
        document_timeout_seconds=0.1,
    )
    session, cookie = service._owner_for_creation(None)
    analyzing = service._create_analyzing_assignment(
        assignment_id="asn_pending",
        source_bytes=SAMPLE_PDF.read_bytes(),
        source_filename="pending.pdf",
        owner_digest=owner_hash(session.owner_id, OWNER_SECRET),
        created_at=now,
        expires_at=session.expires_at,
    )

    current = await service.get_assignment(
        assignment_id=analyzing.manifest.assignment_id,
        owner_cookie=cookie,
    )
    assert current.status.value == "analyzing"
    assert current.source.page_count is None
    assert current.questions == []

    service._now = lambda: now + timedelta(seconds=1)
    recovered = await service.get_assignment(
        assignment_id=analyzing.manifest.assignment_id,
        owner_cookie=cookie,
    )
    assert recovered.status.value == "analysis_failed"
    assert recovered.source.page_count is None
    assert recovered.warnings[0].code == "analysis_timeout"
    assert service.manifests.load(analyzing.manifest.assignment_id).manifest.failure_code == (
        "analysis_timeout"
    )
