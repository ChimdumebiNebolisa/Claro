"""Claros V2 FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI

from backend.api.errors import install_error_handlers
from backend.api.models import HealthResponse
from backend.api.router import router as api_v2_router
from backend.config import Settings
from backend.service import build_assignment_service
from backend.telemetry import OperationalTelemetryMiddleware
from backend.web import (
    AssignmentUploadLimitMiddleware,
    BrowserBoundaryMiddleware,
    HealthProbeTrustedHostMiddleware,
    install_spa_routes,
)


def create_app(
    *,
    settings: Settings | None = None,
    assignment_service: Any | None = None,
    dist_path: Path | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    app = FastAPI(
        title="Claros V2 API",
        version="2.0.0",
        openapi_url=(
            None if resolved_settings.environment == "production" else "/api/v2/openapi.json"
        ),
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = resolved_settings
    app.state.assignment_service = assignment_service or build_assignment_service(resolved_settings)
    install_error_handlers(app)
    app.include_router(api_v2_router)

    @app.get("/health", response_model=HealthResponse, operation_id="health")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    if dist_path is not None:
        install_spa_routes(app, dist_path=dist_path)
    app.add_middleware(
        AssignmentUploadLimitMiddleware,
        max_upload_bytes=resolved_settings.max_upload_bytes,
    )
    app.add_middleware(
        HealthProbeTrustedHostMiddleware,
        allowed_hosts=resolved_settings.trusted_hosts,
    )
    app.add_middleware(BrowserBoundaryMiddleware, settings=resolved_settings)
    app.add_middleware(OperationalTelemetryMiddleware)

    return app


app = create_app(dist_path=Path(__file__).resolve().parents[1] / "dist")
