"""Stable student-safe API errors and FastAPI handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.models import ErrorDetail, ErrorEnvelope


class ClarosError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        recoverable: bool,
        status_code: int,
        version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.status_code = status_code
        self.version = version


def error_response(error: ClarosError) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=error.code,
            message=error.message,
            recoverable=error.recoverable,
        ),
        version=error.version,
    )
    headers = {}
    if error.version is not None:
        headers["ETag"] = f'"assignment-version-{error.version}"'
    return JSONResponse(
        status_code=error.status_code,
        content=envelope.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ClarosError)
    async def handle_claros_error(_request: Request, error: ClarosError) -> JSONResponse:
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            ClarosError(
                code="invalid_request",
                message="The request could not be accepted. Check it and try again.",
                recoverable=True,
                status_code=422,
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        is_missing_api = error.status_code == 404 and request.url.path.startswith("/api/")
        code = "route_not_found" if is_missing_api else "request_rejected"
        message = (
            "The requested API route does not exist."
            if is_missing_api
            else "The request could not be completed."
        )
        return error_response(
            ClarosError(
                code=code,
                message=message,
                recoverable=False,
                status_code=error.status_code,
            )
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, _error: Exception) -> JSONResponse:
        return error_response(
            ClarosError(
                code="internal_error",
                message="Claros could not complete that action.",
                recoverable=True,
                status_code=500,
            )
        )
