"""Privacy-safe operational telemetry for HTTP request outcomes."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from time import perf_counter

from starlette.types import ASGIApp

LOGGER = logging.getLogger("claros.operations")
MAX_ERROR_BODY_BYTES = 4096
MAX_DURATION_MS = 300_000.0
HTTP_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_IDENTIFIERS = r"[^/]+"

_ROUTES: tuple[tuple[str, re.Pattern[str], str, str, str], ...] = (
    (
        "GET",
        re.compile(r"^/health$"),
        "/health",
        "health",
        "health",
    ),
    (
        "POST",
        re.compile(r"^/api/v2/assignments$"),
        "/api/v2/assignments",
        "create_assignment",
        "upload",
    ),
    (
        "GET",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}$"),
        "/api/v2/assignments/{assignment_id}",
        "get_assignment",
        "api",
    ),
    (
        "GET",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/source$"),
        "/api/v2/assignments/{assignment_id}/source",
        "get_assignment_source",
        "api",
    ),
    (
        "HEAD",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/source$"),
        "/api/v2/assignments/{assignment_id}/source",
        "head_assignment_source",
        "api",
    ),
    (
        "GET",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/pages/{_IDENTIFIERS}/context$"),
        "/api/v2/assignments/{assignment_id}/pages/{page_number}/context",
        "get_page_context",
        "api",
    ),
    (
        "POST",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/questions/{_IDENTIFIERS}/candidates$"),
        "/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        "create_candidate",
        "api",
    ),
    (
        "POST",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/questions/{_IDENTIFIERS}/rephrase$"),
        "/api/v2/assignments/{assignment_id}/questions/{question_id}/rephrase",
        "request_rephrase",
        "api",
    ),
    (
        "POST",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/questions/{_IDENTIFIERS}/review$"),
        "/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        "create_review",
        "api",
    ),
    (
        "POST",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/questions/{_IDENTIFIERS}/confirm$"),
        "/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        "confirm_answer",
        "api",
    ),
    (
        "PATCH",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/questions/{_IDENTIFIERS}/answer$"),
        "/api/v2/assignments/{assignment_id}/questions/{question_id}/answer",
        "begin_answer_revision",
        "api",
    ),
    (
        "POST",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/exports$"),
        "/api/v2/assignments/{assignment_id}/exports",
        "create_export",
        "api",
    ),
    (
        "GET",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/exports/{_IDENTIFIERS}$"),
        "/api/v2/assignments/{assignment_id}/exports/{export_id}",
        "get_export",
        "api",
    ),
    (
        "GET",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/exports/{_IDENTIFIERS}/download$"),
        "/api/v2/assignments/{assignment_id}/exports/{export_id}/download",
        "download_export",
        "api",
    ),
    (
        "HEAD",
        re.compile(rf"^/api/v2/assignments/{_IDENTIFIERS}/exports/{_IDENTIFIERS}/download$"),
        "/api/v2/assignments/{assignment_id}/exports/{export_id}/download",
        "head_export",
        "api",
    ),
    (
        "POST",
        re.compile(r"^/api/v2/realtime/client-secret$"),
        "/api/v2/realtime/client-secret",
        "issue_realtime_client_secret",
        "api",
    ),
)


def _route_identity(method: str, path: str) -> tuple[str, str, str]:
    for expected_method, pattern, template, operation, stage in _ROUTES:
        if method == expected_method and pattern.fullmatch(path):
            return template, operation, stage
    if method in {"GET", "HEAD"} and not path.startswith("/api/"):
        return "/{request_path:path}", "spa_or_asset", "frontend"
    return "<unmatched>", "route_not_found", "routing"


def _extract_error_code(payload: bytes, status_code: int) -> str | None:
    if status_code < 400:
        return None
    try:
        decoded = json.loads(payload)
        error = decoded.get("error") if isinstance(decoded, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        code = None
    if isinstance(code, str) and _ERROR_CODE.fullmatch(code):
        return code
    return f"http_{status_code}" if 400 <= status_code <= 599 else "http_error"


class OperationalTelemetryMiddleware:
    """Log bounded, content-free request outcome fields as one JSON event."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[[], Awaitable[dict[str, object]]],
        send: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        requested_method = str(scope.get("method", "")).upper()
        method = requested_method if requested_method in HTTP_METHODS else "OTHER"
        path = str(scope.get("path", ""))
        route_template, operation, stage = _route_identity(method, path)
        started_at = perf_counter()
        status_code = 500
        captures_error_body = False
        error_body: bytearray | None = bytearray()
        forced_error_code: str | None = None

        async def observe_response(message: dict[str, object]) -> None:
            nonlocal captures_error_body, error_body, status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = message.get("headers", [])
                content_types = [
                    value
                    for name, value in headers
                    if isinstance(name, bytes)
                    and isinstance(value, bytes)
                    and name.lower() == b"content-type"
                ]
                captures_error_body = status_code >= 400 and any(
                    value.lower().startswith(b"application/json") for value in content_types
                )
            elif message["type"] == "http.response.body" and captures_error_body:
                chunk = message.get("body", b"")
                if not isinstance(chunk, bytes):
                    chunk = bytes(chunk)
                if error_body is not None and len(error_body) + len(chunk) <= MAX_ERROR_BODY_BYTES:
                    error_body.extend(chunk)
                else:
                    error_body = None
            await send(message)

        try:
            await self.app(scope, receive, observe_response)
        except Exception:
            forced_error_code = "internal_error"
            status_code = 500
            error_body = None
            raise
        finally:
            elapsed_ms = min(max((perf_counter() - started_at) * 1000, 0.0), MAX_DURATION_MS)
            error_code = forced_error_code or _extract_error_code(
                bytes(error_body or b""), status_code
            )
            event = {
                "duration_ms": round(elapsed_ms, 3),
                "error_code": error_code,
                "event": "http_request",
                "method": method,
                "operation": operation,
                "route_template": route_template,
                "stage": stage,
                "status": status_code,
            }
            LOGGER.info(json.dumps(event, separators=(",", ":"), sort_keys=True))
