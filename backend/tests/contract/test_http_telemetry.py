from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.telemetry import OperationalTelemetryMiddleware
from backend.web import MULTIPART_OVERHEAD_BYTES


class _UnusedService:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"assignment service was reached through {name}")


def _upload_scope(*, content_length: int | None = None) -> dict[str, object]:
    headers = [
        (b"host", b"claros.test"),
        (b"origin", b"https://claros.test"),
        (b"content-type", b"multipart/form-data; boundary=claros-boundary"),
    ]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode("ascii")))
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/v2/assignments",
        "raw_path": b"/api/v2/assignments",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("claros.test", 443),
        "root_path": "",
    }


async def _call_upload(
    app: FastAPI,
    *,
    scope: dict[str, object],
    messages: list[dict[str, object]],
) -> list[dict[str, object]]:
    pending = iter(messages)
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return next(pending)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _response(sent: list[dict[str, object]]) -> tuple[int, dict[str, object]]:
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return int(start["status"]), json.loads(body)


def test_oversized_content_length_is_rejected_without_reading_or_parsing(
    monkeypatch: Any,
) -> None:
    settings = Settings(
        environment="test",
        public_origin="https://claros.test",
        max_upload_bytes=32,
    )
    app = create_app(settings=settings, assignment_service=_UnusedService())

    async def parser_must_not_run(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("multipart parser was reached")

    monkeypatch.setattr("starlette.formparsers.MultiPartParser.parse", parser_must_not_run)
    cap = settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
    sent = asyncio.run(
        _call_upload(
            app,
            scope=_upload_scope(content_length=cap + 1),
            messages=[],
        )
    )

    status, payload = _response(sent)
    assert status == 413
    assert payload == {
        "error": {
            "code": "file_too_large",
            "message": "This PDF is larger than the 10 MiB limit.",
            "recoverable": True,
        }
    }


def test_oversized_chunked_body_is_rejected_before_parser_and_service(
    monkeypatch: Any,
) -> None:
    settings = Settings(
        environment="test",
        public_origin="https://claros.test",
        max_upload_bytes=16,
    )
    app = create_app(settings=settings, assignment_service=_UnusedService())

    async def parser_must_not_run(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("multipart parser was reached")

    monkeypatch.setattr("starlette.formparsers.MultiPartParser.parse", parser_must_not_run)
    cap = settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
    sensitive_body = b"student worksheet and exact answer must not appear" + b"x" * cap
    sent = asyncio.run(
        _call_upload(
            app,
            scope=_upload_scope(),
            messages=[
                {"type": "http.request", "body": sensitive_body, "more_body": True},
            ],
        )
    )

    status, payload = _response(sent)
    assert status == 413
    assert payload["error"]["code"] == "file_too_large"
    assert "student worksheet" not in json.dumps(payload)


def test_telemetry_uses_route_templates_and_never_logs_request_content(
    caplog: Any,
) -> None:
    app = FastAPI()

    @app.post("/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates")
    async def fail_candidate(assignment_id: str, question_id: str) -> JSONResponse:
        del assignment_id, question_id
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "version_conflict",
                    "message": "Refresh the assignment and try again.",
                    "recoverable": True,
                }
            },
        )

    app.add_middleware(OperationalTelemetryMiddleware)
    client = TestClient(app)
    secrets = {
        "assignment": "asn_private_student_identifier",
        "question": "q_private_worksheet_identifier",
        "answer": "A private exact worksheet answer",
        "cookie": "signed-owner-cookie-value",
        "token": "browser-auth-token-value",
        "query": "private-query-value",
    }
    caplog.set_level(logging.INFO, logger="claros.operations")

    response = client.post(
        (
            f"/api/v2/assignments/{secrets['assignment']}/questions/"
            f"{secrets['question']}/candidates?debug={secrets['query']}"
        ),
        json={"text": secrets["answer"]},
        headers={
            "Authorization": f"Bearer {secrets['token']}",
            "Cookie": f"claros_owner={secrets['cookie']}",
        },
    )

    assert response.status_code == 409
    records = [record for record in caplog.records if record.name == "claros.operations"]
    assert len(records) == 1
    raw_event = records[0].getMessage()
    event = json.loads(raw_event)
    assert event == {
        "duration_ms": event["duration_ms"],
        "error_code": "version_conflict",
        "event": "http_request",
        "method": "POST",
        "operation": "create_candidate",
        "route_template": (
            "/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates"
        ),
        "stage": "api",
        "status": 409,
    }
    assert 0 <= event["duration_ms"] <= 300_000
    assert all(secret not in raw_event for secret in secrets.values())


def test_telemetry_does_not_log_raw_exceptions(caplog: Any) -> None:
    app = FastAPI()

    @app.get("/api/v2/assignments/{assignment_id}")
    async def explode(assignment_id: str) -> None:
        del assignment_id
        raise RuntimeError("private worksheet text in provider exception")

    app.add_middleware(OperationalTelemetryMiddleware)
    caplog.set_level(logging.INFO, logger="claros.operations")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v2/assignments/asn_private_exception"
    )

    assert response.status_code == 500
    raw_event = next(
        record.getMessage() for record in caplog.records if record.name == "claros.operations"
    )
    event = json.loads(raw_event)
    assert event["error_code"] == "internal_error"
    assert "private worksheet" not in raw_event
    assert "RuntimeError" not in raw_event


def test_health_does_not_touch_assignment_service_and_logs_only_safe_fields(
    caplog: Any,
) -> None:
    app = create_app(
        settings=Settings(environment="test"),
        assignment_service=_UnusedService(),
    )
    caplog.set_level(logging.INFO, logger="claros.operations")

    response = TestClient(app).get("/health?token=private-health-query")

    assert response.status_code == 200
    event = json.loads(
        next(record.getMessage() for record in caplog.records if record.name == "claros.operations")
    )
    assert event["operation"] == "health"
    assert event["stage"] == "health"
    assert event["error_code"] is None
    assert "private-health-query" not in json.dumps(event)
