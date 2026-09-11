"""HTTP boundaries shared by the API and bundled Vite application."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp

from backend.api.models import ErrorDetail, ErrorEnvelope
from backend.config import CanonicalOrigin, Settings, canonical_origin

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ASSIGNMENT_UPLOAD_PATH = "/api/v2/assignments"
MULTIPART_OVERHEAD_BYTES = 64 * 1024
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; "
        "img-src 'self' data: blob:; connect-src 'self'; "
        "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _upload_too_large_response() -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code="file_too_large",
            message="This PDF is larger than the 10 MiB limit.",
            recoverable=True,
        )
    )
    return JSONResponse(
        status_code=413,
        content=envelope.model_dump(mode="json", exclude_none=True),
    )


def _declared_content_length(scope: dict[str, object]) -> int | None:
    values = [
        value
        for name, value in scope.get("headers", [])
        if isinstance(name, bytes) and name.lower() == b"content-length"
    ]
    if len(values) != 1 or not isinstance(values[0], bytes):
        return None
    try:
        value = int(values[0].decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None
    return value if value >= 0 else None


class AssignmentUploadLimitMiddleware:
    """Bound assignment bodies before Starlette's multipart parser runs."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_upload_bytes: int,
        multipart_overhead_bytes: int = MULTIPART_OVERHEAD_BYTES,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_upload_bytes + multipart_overhead_bytes

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[[], Awaitable[dict[str, object]]],
        send: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        if not (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == ASSIGNMENT_UPLOAD_PATH
        ):
            await self.app(scope, receive, send)
            return

        declared_length = _declared_content_length(scope)
        if declared_length is not None and declared_length > self.max_body_bytes:
            await _upload_too_large_response()(scope, receive, send)
            return

        buffered_messages: list[dict[str, Any]] = []
        received_bytes = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue

            body = message.get("body", b"")
            if not isinstance(body, bytes):
                body = bytes(body)
            received_bytes += len(body)
            if received_bytes > self.max_body_bytes:
                await _upload_too_large_response()(scope, receive, send)
                return
            buffered_messages.append(
                {
                    "type": "http.request",
                    "body": body,
                    "more_body": bool(message.get("more_body", False)),
                }
            )
            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_receive() -> dict[str, object]:
            nonlocal message_index
            if message_index >= len(buffered_messages):
                return {"type": "http.disconnect"}
            message = buffered_messages[message_index]
            message_index += 1
            return message

        await self.app(scope, replay_receive, send)


def _request_origin_matches(headers: list[str], expected: CanonicalOrigin) -> bool:
    if len(headers) != 1:
        return False
    try:
        return canonical_origin(headers[0]) == expected
    except ValueError:
        return False


class HealthProbeTrustedHostMiddleware:
    """Validate request hosts while keeping the inert health probe reachable."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: tuple[str, ...]) -> None:
        self.app = app
        self.trusted_hosts = TrustedHostMiddleware(
            app,
            allowed_hosts=list(allowed_hosts),
            www_redirect=False,
        )

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[[], Awaitable[dict[str, object]]],
        send: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        if scope["type"] == "http" and scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        await self.trusted_hosts(scope, receive, send)


class BrowserBoundaryMiddleware:
    """Reject cross-site API mutations and attach baseline browser headers."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.expected_origin = canonical_origin(settings.public_origin)

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[[], Awaitable[dict[str, object]]],
        send: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_path = str(scope.get("path", ""))
        is_api_mutation = (
            request_path == "/api/v2" or request_path.startswith("/api/v2/")
        ) and request.method in MUTATING_METHODS
        origins = request.headers.getlist("origin")
        fetch_sites = request.headers.getlist("sec-fetch-site")
        origin_is_invalid = not _request_origin_matches(origins, self.expected_origin)
        browser_reports_cross_site = any(
            fetch_site.casefold() == "cross-site" for fetch_site in fetch_sites
        )

        if is_api_mutation and (origin_is_invalid or browser_reports_cross_site):
            envelope = ErrorEnvelope(
                error=ErrorDetail(
                    code="origin_forbidden",
                    message="This request did not come from the Claros application.",
                    recoverable=False,
                )
            )
            response = JSONResponse(
                status_code=403,
                content=envelope.model_dump(mode="json", exclude_none=True),
            )
            for name, value in SECURITY_HEADERS.items():
                response.headers[name] = value
            await response(scope, receive, send)
            return

        async def send_with_headers(message: dict[str, object]) -> None:
            if message["type"] == "http.response.start":
                mutable_headers = list(message.get("headers", []))
                existing = {key.decode("latin-1").casefold() for key, _value in mutable_headers}
                for name, value in SECURITY_HEADERS.items():
                    if name.casefold() not in existing:
                        mutable_headers.append(
                            (name.lower().encode("latin-1"), value.encode("latin-1"))
                        )
                if (
                    request_path == "/api/v2" or request_path.startswith("/api/v2/")
                ) and "cache-control" not in existing:
                    mutable_headers.append((b"cache-control", b"private, no-store"))
                message["headers"] = mutable_headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


def install_spa_routes(app: FastAPI, *, dist_path: Path) -> None:
    """Serve safe static files and route-shaped paths from one FastAPI process."""

    resolved_dist = dist_path.resolve()
    index_path = resolved_dist / "index.html"

    def resolved_asset_path(request_path: str) -> Path | None:
        candidate = (resolved_dist / request_path.lstrip("/")).resolve()
        if candidate == resolved_dist or resolved_dist not in candidate.parents:
            return None
        return candidate if candidate.is_file() else None

    @app.api_route(
        "/{request_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def spa_or_asset(request_path: str) -> Response:
        if request_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "route_not_found",
                        "message": "The requested API route does not exist.",
                        "recoverable": False,
                    }
                },
            )

        asset = resolved_asset_path(request_path)
        if asset is not None:
            return FileResponse(asset)

        final_segment = request_path.rsplit("/", 1)[-1]
        if "." in final_segment or not index_path.is_file():
            return Response(status_code=404)
        return FileResponse(index_path, media_type="text/html")
