from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.api.dependencies import (
    get_assignment_service,
    get_owner_cookie,
    get_settings,
)
from backend.api.errors import ClarosError, install_error_handlers
from backend.config import Settings
from backend.web import BrowserBoundaryMiddleware, install_spa_routes


def _request(app: FastAPI, *, cookie: str = "") -> Request:
    headers = [(b"cookie", cookie.encode("ascii"))] if cookie else []
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("claros.test", 443),
            "root_path": "",
            "app": app,
        }
    )


def test_dependencies_read_app_state_and_custom_cookie_name() -> None:
    app = FastAPI()
    settings = Settings(environment="test", owner_cookie_name="custom_owner")
    service = object()
    app.state.settings = settings
    app.state.assignment_service = service
    request = _request(app, cookie="claros_owner=default; custom_owner=custom")

    assert get_settings(request) is settings
    assert get_assignment_service(request) is service
    assert get_owner_cookie(request, "default") == "custom"

    default_app = FastAPI()
    default_app.state.settings = Settings(environment="test")
    assert get_owner_cookie(_request(default_app, cookie="claros_owner=cookie"), "bound") == "bound"


def _error_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/versioned")
    async def versioned_error() -> None:
        raise ClarosError(
            code="version_conflict",
            message="Refresh the assignment and try again.",
            recoverable=True,
            status_code=409,
            version=6,
        )

    @app.get("/number/{value}")
    async def validated_path(value: int) -> dict[str, int]:
        return {"value": value}

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail="provider detail must not leak")

    @app.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("worksheet answer must not leak")

    return app


def test_error_handlers_emit_stable_safe_envelopes_and_version_etag() -> None:
    client = TestClient(_error_app(), raise_server_exceptions=False)

    versioned = client.get("/versioned")
    assert versioned.status_code == 409
    assert versioned.headers["etag"] == '"assignment-version-6"'
    assert versioned.json() == {
        "error": {
            "code": "version_conflict",
            "message": "Refresh the assignment and try again.",
            "recoverable": True,
        },
        "version": 6,
    }

    invalid = client.get("/number/not-an-integer")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request"

    rejected = client.get("/teapot")
    assert rejected.status_code == 418
    assert rejected.json()["error"] == {
        "code": "request_rejected",
        "message": "The request could not be completed.",
        "recoverable": False,
    }
    assert "provider detail" not in rejected.text

    unexpected = client.get("/unexpected")
    assert unexpected.status_code == 500
    assert unexpected.json()["error"]["code"] == "internal_error"
    assert "worksheet answer" not in unexpected.text


def _boundary_app() -> FastAPI:
    app = FastAPI()

    @app.api_route(
        "/api/v2/default",
        methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def default_api_response() -> Response:
        return Response("ok")

    @app.api_route("/api/v2/preserved", methods=["GET", "POST"])
    async def preserved_api_response() -> Response:
        return Response(
            "ok",
            headers={
                "Cache-Control": "private, max-age=5",
                "X-Frame-Options": "DENY",
            },
        )

    @app.post("/api/v20/not-v2")
    async def adjacent_api_response() -> Response:
        return Response("adjacent")

    @app.get("/plain")
    async def plain_response() -> Response:
        return Response("plain")

    app.add_middleware(
        BrowserBoundaryMiddleware,
        settings=Settings(environment="test", public_origin="https://claros.test"),
    )
    return app


def test_browser_middleware_origin_and_cache_boundaries() -> None:
    client = TestClient(_boundary_app())

    invalid_origin = client.post(
        "/api/v2/default",
        headers={"Origin": "not-an-origin"},
    )
    assert invalid_origin.status_code == 403

    equivalent_origin = client.post(
        "/api/v2/default",
        headers={"Origin": "https://CLAROS.TEST:443"},
    )
    assert equivalent_origin.status_code == 200
    assert equivalent_origin.headers["cache-control"] == "private, no-store"

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        missing_origin = client.request(method, "/api/v2/default")
        assert missing_origin.status_code == 403
        assert missing_origin.json()["error"]["code"] == "origin_forbidden"

    assert (
        client.head(
            "/api/v2/default",
            headers={"Origin": "https://attacker.test", "Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 200
    )
    assert (
        client.options(
            "/api/v2/default",
            headers={"Origin": "https://attacker.test", "Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 200
    )

    # Cross-origin metadata does not block reads, and an adjacent prefix is not `/api/v2/`.
    assert (
        client.get(
            "/api/v2/default",
            headers={"Origin": "https://attacker.test", "Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v20/not-v2",
            headers={"Origin": "https://attacker.test", "Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 200
    )

    preserved = client.get("/api/v2/preserved")
    assert preserved.headers["cache-control"] == "private, max-age=5"
    assert preserved.headers.get_list("x-frame-options") == ["DENY"]

    plain = client.get("/plain")
    assert "cache-control" not in plain.headers
    assert plain.headers["x-content-type-options"] == "nosniff"


def test_browser_middleware_passes_non_http_scopes_through() -> None:
    observed: list[dict[str, object]] = []
    sent: list[dict[str, object]] = []

    async def inner(
        scope: dict[str, object],
        _receive: Any,
        send: Any,
    ) -> None:
        observed.append(scope)
        await send({"type": "lifespan.complete"})

    async def receive() -> dict[str, object]:
        return {"type": "lifespan.shutdown"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = BrowserBoundaryMiddleware(
        inner,
        settings=Settings(environment="test", public_origin="https://claros.test"),
    )
    scope: dict[str, object] = {"type": "lifespan"}
    asyncio.run(middleware(scope, receive, send))

    assert observed == [scope]
    assert sent == [{"type": "lifespan.complete"}]


def test_spa_fallback_without_index_fails_closed_for_routes_and_assets(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    app = FastAPI()
    install_spa_routes(app, dist_path=dist)
    client = TestClient(app)

    assert client.get("/").status_code == 404
    assert client.get("/app/asg_test_01").status_code == 404
    assert client.get("/missing.js").status_code == 404
    missing_api = client.get("/api/v2/missing")
    assert missing_api.status_code == 404
    assert missing_api.json()["error"]["code"] == "route_not_found"
