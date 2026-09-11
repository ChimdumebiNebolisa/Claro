"""Frozen `/api/v2` route signatures."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Header, Query, Request, Response, UploadFile, status

from backend.api.dependencies import OwnerCookieDependency, ServiceDependency, SettingsDependency
from backend.api.errors import ClarosError
from backend.api.models import (
    AssignmentResponse,
    BeginRevisionRequest,
    BeginRevisionResponse,
    CandidateRequest,
    CandidateResponse,
    ConfirmRequest,
    ConfirmResponse,
    CreateExportRequest,
    ErrorEnvelope,
    ExportResponse,
    PageContextResponse,
    RealtimeCredentialRequest,
    RealtimeCredentialResponse,
    RephraseRequest,
    RephraseResponse,
    ReviewRequest,
    ReviewResponse,
)

router = APIRouter(prefix="/api/v2")
error_responses = {
    400: {"model": ErrorEnvelope},
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    410: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope},
    415: {"model": ErrorEnvelope},
    416: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}
etag_header = {
    "description": "Opaque validator for the returned assignment version.",
    "schema": {"type": "string", "example": '"assignment-version-2"'},
}
content_etag_header = {
    "description": "Immutable object hash and storage-generation validator.",
    "schema": {"type": "string", "example": '"sha256-abc123-g1"'},
}


def versioned_responses(*success_statuses: int) -> dict[int, dict[str, object]]:
    responses: dict[int, dict[str, object]] = dict(error_responses)
    for success_status in success_statuses:
        responses[success_status] = {"headers": {"ETag": etag_header}}
    return responses


def content_responses() -> dict[int, dict[str, object]]:
    responses: dict[int, dict[str, object]] = dict(error_responses)
    responses[status.HTTP_200_OK] = {"headers": {"ETag": content_etag_header}}
    responses[status.HTTP_206_PARTIAL_CONTENT] = {"headers": {"ETag": content_etag_header}}
    return responses


def set_version_etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"assignment-version-{version}"'


@router.post(
    "/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_assignment",
    responses=versioned_responses(status.HTTP_201_CREATED),
)
async def create_assignment(
    request: Request,
    response: Response,
    service: ServiceDependency,
    settings: SettingsDependency,
    owner_cookie: OwnerCookieDependency,
    file: Annotated[UploadFile | None, File()] = None,
    sample_id: Annotated[str | None, Form(min_length=1, max_length=96)] = None,
) -> AssignmentResponse:
    if (file is None) == (sample_id is None):
        raise ClarosError(
            code="invalid_assignment_input",
            message="Choose one PDF or the sample worksheet.",
            recoverable=True,
            status_code=422,
        )
    result, owner_cookie = await service.create_assignment(
        file=file,
        sample_id=sample_id,
        settings=settings,
        owner_cookie=owner_cookie,
        rate_subject=request.client.host if request.client else "unknown-client",
    )
    set_version_etag(response, result.version)
    response.set_cookie(
        key=settings.owner_cookie_name,
        value=owner_cookie,
        max_age=settings.assignment_ttl_seconds,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="lax",
        path="/",
    )
    return result


@router.get(
    "/assignments/{assignment_id}",
    response_model=AssignmentResponse,
    operation_id="get_assignment",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def get_assignment(
    assignment_id: str,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> AssignmentResponse:
    result = await service.get_assignment(
        assignment_id=assignment_id,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


async def source_response(
    *,
    assignment_id: str,
    owner_cookie: str | None,
    range_header: str | None,
    service: ServiceDependency,
    head_only: bool,
) -> Response:
    return await service.read_source(
        assignment_id=assignment_id,
        owner_cookie=owner_cookie,
        range_header=range_header,
        head_only=head_only,
    )


@router.get(
    "/assignments/{assignment_id}/source",
    response_class=Response,
    operation_id="get_assignment_source",
    responses=content_responses(),
)
async def get_assignment_source(
    assignment_id: str,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    return await source_response(
        assignment_id=assignment_id,
        owner_cookie=owner_cookie,
        range_header=range_header,
        service=service,
        head_only=False,
    )


@router.head(
    "/assignments/{assignment_id}/source",
    response_class=Response,
    operation_id="head_assignment_source",
    responses=content_responses(),
)
async def head_assignment_source(
    assignment_id: str,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    return await source_response(
        assignment_id=assignment_id,
        owner_cookie=owner_cookie,
        range_header=range_header,
        service=service,
        head_only=True,
    )


@router.get(
    "/assignments/{assignment_id}/pages/{page_number}/context",
    response_model=PageContextResponse,
    operation_id="get_page_context",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def get_page_context(
    assignment_id: str,
    page_number: int,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
    question_id: Annotated[str, Query(min_length=1, max_length=96)],
    preview: Annotated[Literal["original", "confirmed"], Query()] = "original",
) -> PageContextResponse:
    result = await service.get_page_context(
        assignment_id=assignment_id,
        page_number=page_number,
        question_id=question_id,
        preview=preview,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


@router.post(
    "/assignments/{assignment_id}/questions/{question_id}/candidates",
    response_model=CandidateResponse,
    operation_id="create_candidate",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def create_candidate(
    assignment_id: str,
    question_id: str,
    body: CandidateRequest,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> CandidateResponse:
    result = await service.create_candidate(
        assignment_id=assignment_id,
        question_id=question_id,
        body=body,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


@router.post(
    "/assignments/{assignment_id}/questions/{question_id}/rephrase",
    response_model=RephraseResponse,
    operation_id="request_rephrase",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def request_rephrase(
    assignment_id: str,
    question_id: str,
    body: RephraseRequest,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> RephraseResponse:
    result = await service.request_rephrase(
        assignment_id=assignment_id,
        question_id=question_id,
        body=body,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


@router.post(
    "/assignments/{assignment_id}/questions/{question_id}/review",
    response_model=ReviewResponse,
    operation_id="create_review",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def create_review(
    assignment_id: str,
    question_id: str,
    body: ReviewRequest,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> ReviewResponse:
    result = await service.create_review(
        assignment_id=assignment_id,
        question_id=question_id,
        body=body,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


@router.post(
    "/assignments/{assignment_id}/questions/{question_id}/confirm",
    response_model=ConfirmResponse,
    operation_id="confirm_answer",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def confirm_answer(
    assignment_id: str,
    question_id: str,
    body: ConfirmRequest,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> ConfirmResponse:
    result = await service.confirm_answer(
        assignment_id=assignment_id,
        question_id=question_id,
        body=body,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


@router.patch(
    "/assignments/{assignment_id}/questions/{question_id}/answer",
    response_model=BeginRevisionResponse,
    operation_id="begin_answer_revision",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def begin_answer_revision(
    assignment_id: str,
    question_id: str,
    body: BeginRevisionRequest,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> BeginRevisionResponse:
    result = await service.begin_revision(
        assignment_id=assignment_id,
        question_id=question_id,
        body=body,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


@router.post(
    "/assignments/{assignment_id}/exports",
    response_model=ExportResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_export",
    responses=versioned_responses(status.HTTP_200_OK, status.HTTP_201_CREATED),
)
async def create_export(
    assignment_id: str,
    body: CreateExportRequest,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> ExportResponse:
    result, replayed = await service.create_export(
        assignment_id=assignment_id,
        body=body,
        owner_cookie=owner_cookie,
    )
    if replayed:
        response.status_code = status.HTTP_200_OK
    set_version_etag(response, result.version)
    return result


@router.get(
    "/assignments/{assignment_id}/exports/{export_id}",
    response_model=ExportResponse,
    operation_id="get_export",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def get_export(
    assignment_id: str,
    export_id: str,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> ExportResponse:
    result = await service.get_export(
        assignment_id=assignment_id,
        export_id=export_id,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result


async def export_download_response(
    *,
    assignment_id: str,
    export_id: str,
    owner_cookie: str | None,
    range_header: str | None,
    service: ServiceDependency,
    head_only: bool,
) -> Response:
    return await service.read_export(
        assignment_id=assignment_id,
        export_id=export_id,
        owner_cookie=owner_cookie,
        range_header=range_header,
        head_only=head_only,
    )


@router.get(
    "/assignments/{assignment_id}/exports/{export_id}/download",
    response_class=Response,
    operation_id="download_export",
    responses=content_responses(),
)
async def download_export(
    assignment_id: str,
    export_id: str,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    return await export_download_response(
        assignment_id=assignment_id,
        export_id=export_id,
        owner_cookie=owner_cookie,
        range_header=range_header,
        service=service,
        head_only=False,
    )


@router.head(
    "/assignments/{assignment_id}/exports/{export_id}/download",
    response_class=Response,
    operation_id="head_export",
    responses=content_responses(),
)
async def head_export(
    assignment_id: str,
    export_id: str,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    return await export_download_response(
        assignment_id=assignment_id,
        export_id=export_id,
        owner_cookie=owner_cookie,
        range_header=range_header,
        service=service,
        head_only=True,
    )


@router.post(
    "/realtime/client-secret",
    response_model=RealtimeCredentialResponse,
    operation_id="issue_realtime_client_secret",
    responses=versioned_responses(status.HTTP_200_OK),
)
async def issue_realtime_client_secret(
    body: RealtimeCredentialRequest,
    response: Response,
    owner_cookie: OwnerCookieDependency,
    service: ServiceDependency,
) -> RealtimeCredentialResponse:
    result = await service.issue_realtime_credential(
        body=body,
        owner_cookie=owner_cookie,
    )
    set_version_etag(response, result.version)
    return result
