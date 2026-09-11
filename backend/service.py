"""Durable application service joining HTTP, storage, domain, and PDF seams."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import quote

import anyio
from fastapi import Response, UploadFile
from fastapi.responses import JSONResponse
from google.api_core.exceptions import DeadlineExceeded as GoogleDeadlineExceeded

from backend.api.errors import ClarosError
from backend.api.models import (
    AssignmentResponse,
    AssignmentStatus,
    BeginRevisionRequest,
    BeginRevisionResponse,
    Candidate,
    CandidateOrigin,
    CandidateRequest,
    CandidateResponse,
    ConfirmedAnswer,
    ConfirmRequest,
    ConfirmResponse,
    CreateExportRequest,
    DirectTypedInteraction,
    DirectVoiceInteraction,
    ExportFailure,
    ExportResponse,
    ExportStatus,
    GuidedFinalInteraction,
    PageContextResponse,
    PageRect,
    Placement,
    PlacementCapability,
    PlacementSummary,
    QuestionProjection,
    RealtimeCredentialRequest,
    RealtimeCredentialResponse,
    RephraseRequest,
    RephraseResponse,
    ReviewRequest,
    ReviewResponse,
    SafeWarning,
    SelectedRephraseInteraction,
    SourceDocument,
    SourceStatus,
    StudentAttribution,
    StudentEditInteraction,
)
from backend.config import Settings
from backend.document import (
    ConfirmedAnswerForExport as DocumentAnswer,
)
from backend.document import (
    DocumentEngineError,
    PreflightLimits,
    QuestionEvidence,
    parse_physical_ir,
    resolve_placement,
)
from backend.document.errors import SAFE_MESSAGES as DOCUMENT_SAFE_MESSAGES
from backend.document.models import CanonicalBox, PhysicalDocumentIR
from backend.document_execution import (
    DocumentExecutionFailure,
    DocumentExecutionTimeout,
    DocumentProcessExecutor,
)
from backend.domain import (
    AssignmentManifest,
    AssignmentVersionConflict,
    CandidateNotFound,
    DomainError,
    InvalidCandidate,
    InvalidCandidateOrigin,
    NoConfirmedAnswers,
    ObjectReference,
    QuestionNotFound,
    QuestionState,
    ReviewTokenExpired,
    ReviewTokenInvalid,
    ReviewTokenStale,
    begin_revision,
    complete_export,
    confirm_candidate,
    confirmed_answers_for_export,
    fail_export,
    issue_review,
    replace_candidate,
    start_export,
)
from backend.domain import (
    AssignmentStatus as DomainAssignmentStatus,
)
from backend.domain import (
    CandidateOrigin as DomainCandidateOrigin,
)
from backend.domain import (
    DirectTypedInteraction as DomainDirectTypedInteraction,
)
from backend.domain import (
    DirectVoiceInteraction as DomainDirectVoiceInteraction,
)
from backend.domain import (
    ExportStatus as DomainExportStatus,
)
from backend.domain import (
    GuidedFinalInteraction as DomainGuidedFinalInteraction,
)
from backend.domain import (
    Placement as DomainPlacement,
)
from backend.domain import (
    PlacementCapability as DomainPlacementCapability,
)
from backend.domain import (
    SelectedRephraseInteraction as DomainSelectedRephraseInteraction,
)
from backend.domain import (
    StudentEditInteraction as DomainStudentEditInteraction,
)
from backend.domain.identifiers import new_identifier
from backend.openpdf import OpenPdfRuntime, select_pdf_engine
from backend.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter
from backend.security import (
    AssignmentAccessDenied,
    OwnerSession,
    OwnerSessionError,
    create_owner_session,
    owner_hash,
    require_assignment_owner,
    verify_owner_session,
)
from backend.storage import (
    GCSObjectStore,
    GenerationConflict,
    LocalObjectStore,
    ManifestRepository,
    ObjectAlreadyExists,
    ObjectIntegrityError,
    ObjectMetadata,
    ObjectNotFound,
    ObjectStore,
    RangeNotSatisfiable,
    StorageError,
    VersionedManifest,
    export_manifest_object_key,
    export_pdf_object_key,
    parse_byte_range,
    physical_ir_object_key,
    source_object_key,
)

_ROOT = Path(__file__).resolve().parents[1]
_SAMPLES = {
    "biology-short-answer": (_ROOT / "public" / "fixtures" / "claros-biology-short-answer.pdf")
}
_SAFE_EXPORT_FAILURES = {
    "invalid_export": "The completed PDF could not be validated safely.",
    "placement_changed": "An answer placement changed. Review that answer again.",
    "publish_failed": "The completed PDF could not be saved. Try again.",
    "stale_physical_ir": "The worksheet analysis changed. Review the answer again.",
    "stale_source": "The worksheet source changed. Review the answer again.",
    "unsupported_glyph": "An answer contains a character the PDF cannot render safely.",
}
_STORAGE_TIMEOUT_MESSAGE = "Worksheet storage took too long. Try again."
_STORAGE_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="claros-storage")
_T = TypeVar("_T")


class _RequestBudgetExpired(TimeoutError):
    pass


@dataclass(frozen=True, slots=True)
class _RequestBudget:
    work_deadline: float
    hard_deadline: float
    clock: Callable[[], float]

    @classmethod
    def start(cls, total_seconds: float, clock: Callable[[], float]) -> _RequestBudget:
        started = clock()
        recovery_seconds = min(30.0, total_seconds * 0.1)
        return cls(
            work_deadline=started + total_seconds - recovery_seconds,
            hard_deadline=started + total_seconds,
            clock=clock,
        )

    def remaining(self, cap_seconds: float, *, recovery: bool = False) -> float:
        deadline = self.hard_deadline if recovery else self.work_deadline
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise _RequestBudgetExpired
        return min(cap_seconds, remaining)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _object_reference(metadata: ObjectMetadata) -> ObjectReference:
    return ObjectReference(
        key=metadata.key,
        generation=metadata.generation,
        sha256=metadata.sha256,
        size_bytes=metadata.size,
        content_type=metadata.content_type,
    )


def _safe_filename(value: str | None) -> str:
    candidate = Path((value or "worksheet.pdf").replace("\\", "/")).name
    candidate = "".join(character for character in candidate if ord(character) >= 32)
    if not candidate or candidate in {".", ".."}:
        candidate = "worksheet.pdf"
    if not candidate.casefold().endswith(".pdf"):
        candidate += ".pdf"
    return candidate[:255]


def _completed_filename(source_filename: str) -> str:
    stem = Path(source_filename).stem[:220] or "worksheet"
    return f"{stem}-completed.pdf"


def _require_matching_object(
    reference: ObjectReference,
    metadata: ObjectMetadata,
    *,
    code: str = "stale_source",
    version: int | None = None,
) -> None:
    if (
        reference.key != metadata.key
        or reference.generation != metadata.generation
        or reference.size_bytes != metadata.size
        or not hmac.compare_digest(reference.sha256, metadata.sha256)
    ):
        raise ClarosError(
            code=code,
            message=_SAFE_EXPORT_FAILURES.get(
                code, "The worksheet data changed. Reload it and try again."
            ),
            recoverable=True,
            status_code=409,
            version=version,
        )


class AssignmentApplicationService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: ObjectStore,
        now: Any = _utc_now,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        document_executor: DocumentProcessExecutor | None = None,
        document_timeout_seconds: float | None = None,
        storage_timeout_seconds: float | None = None,
        request_timeout_seconds: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.store = store
        self.manifests = ManifestRepository(store)
        self._now = now
        self.document_executor = document_executor or DocumentProcessExecutor()
        self._document_timeout_seconds = (
            float(document_timeout_seconds)
            if document_timeout_seconds is not None
            else float(settings.request_timeout_seconds)
        )
        self._storage_timeout_seconds = (
            float(storage_timeout_seconds)
            if storage_timeout_seconds is not None
            else float(settings.request_timeout_seconds)
        )
        self._request_timeout_seconds = (
            float(request_timeout_seconds)
            if request_timeout_seconds is not None
            else float(settings.request_timeout_seconds)
        )
        self._monotonic = monotonic
        if (
            self._document_timeout_seconds <= 0
            or self._storage_timeout_seconds <= 0
            or self._request_timeout_seconds <= 0
        ):
            raise ValueError("service deadlines must be positive")
        self.rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            secret=settings.cookie_secret.get_secret_value()
        )

    async def create_assignment(
        self,
        *,
        file: UploadFile | None,
        sample_id: str | None,
        settings: Settings,
        owner_cookie: str | None = None,
        rate_subject: str = "anonymous",
    ) -> tuple[AssignmentResponse, str]:
        budget = _RequestBudget.start(self._request_timeout_seconds, self._monotonic)
        self._check_rate_limit(
            scope="upload-client",
            subject=rate_subject,
            limit=settings.upload_rate_limit,
            window_seconds=settings.upload_rate_window_seconds,
        )
        session, returned_cookie = self._owner_for_creation(owner_cookie)
        self._check_rate_limit(
            scope="upload-owner",
            subject=session.owner_id,
            limit=settings.upload_rate_limit,
            window_seconds=settings.upload_rate_window_seconds,
        )
        if sample_id is not None:
            path = _SAMPLES.get(sample_id)
            if path is None or not path.is_file():
                raise ClarosError(
                    code="sample_not_found",
                    message="That sample worksheet is unavailable.",
                    recoverable=True,
                    status_code=404,
                )
            source_bytes = await anyio.to_thread.run_sync(path.read_bytes)
            source_filename = path.name
        else:
            if file is None:
                raise ClarosError(
                    code="invalid_assignment_input",
                    message="Choose one PDF or the sample worksheet.",
                    recoverable=True,
                    status_code=422,
                )
            if file.content_type not in {"application/pdf", "application/octet-stream"}:
                raise ClarosError(
                    code="unsupported_media_type",
                    message="Choose a PDF file.",
                    recoverable=True,
                    status_code=415,
                )
            source_bytes = await file.read(settings.max_upload_bytes + 1)
            source_filename = _safe_filename(file.filename)

        if len(source_bytes) > settings.max_upload_bytes:
            raise ClarosError(
                code="file_too_large",
                message="This PDF is larger than the 10 MiB limit.",
                recoverable=True,
                status_code=413,
            )

        limits = PreflightLimits(
            max_upload_bytes=settings.max_upload_bytes,
            max_pages=settings.max_pages,
            max_questions=settings.max_questions,
        )
        assignment_id = new_identifier("asn")
        created_at = self._now().astimezone(UTC)
        owner_digest = owner_hash(session.owner_id, settings.cookie_secret.get_secret_value())
        try:
            analyzing = await self._run_storage(
                partial(
                    self._create_analyzing_assignment,
                    assignment_id=assignment_id,
                    source_bytes=source_bytes,
                    source_filename=source_filename,
                    owner_digest=owner_digest,
                    created_at=created_at,
                    expires_at=session.expires_at,
                ),
                timeout_seconds=budget.remaining(self._storage_timeout_seconds),
                mutation=True,
            )
        except _RequestBudgetExpired as error:
            raise ClarosError(
                code="analysis_timeout",
                message="Worksheet checking took too long. Try again.",
                recoverable=True,
                status_code=503,
            ) from error

        try:
            analysis = await self.document_executor.analyze(
                source_bytes,
                limits=limits,
                timeout_seconds=budget.remaining(self._document_timeout_seconds),
            )
        except (DocumentExecutionTimeout, _RequestBudgetExpired):
            failed = await self._record_analysis_failure(
                analyzing,
                "analysis_timeout",
                budget=budget,
            )
            return self._assignment_response(failed.manifest, None), returned_cookie
        except DocumentEngineError as error:
            failed = await self._record_analysis_failure(analyzing, error.code, budget=budget)
            return self._assignment_response(failed.manifest, None), returned_cookie
        except DocumentExecutionFailure:
            failed = await self._record_analysis_failure(
                analyzing,
                "analysis_failed",
                budget=budget,
            )
            return self._assignment_response(failed.manifest, None), returned_cookie

        try:
            ready = await self._run_storage(
                partial(
                    self._finish_analysis,
                    analyzing,
                    analysis.physical_ir,
                    analysis.questions,
                ),
                version=analyzing.manifest.version,
                timeout_seconds=budget.remaining(self._storage_timeout_seconds),
                mutation=True,
            )
        except _RequestBudgetExpired:
            failed = await self._record_analysis_failure(
                analyzing,
                "analysis_timeout",
                budget=budget,
            )
            return self._assignment_response(failed.manifest, None), returned_cookie
        except ClarosError as error:
            failed = await self._record_analysis_failure(
                analyzing,
                "analysis_failed",
                budget=budget,
            )
            if failed.manifest.status != DomainAssignmentStatus.ANALYSIS_FAILED:
                raise error
            return self._assignment_response(failed.manifest, None), returned_cookie
        return self._assignment_response(ready.manifest, analysis.physical_ir), returned_cookie

    async def get_assignment(
        self, *, assignment_id: str, owner_cookie: str | None
    ) -> AssignmentResponse:
        versioned, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        versioned = await self._recover_stale_analysis(versioned)
        physical_ir = (
            await self._run_storage(
                partial(self._load_ir, versioned.manifest), version=versioned.manifest.version
            )
            if versioned.manifest.status == DomainAssignmentStatus.READY
            else None
        )
        return self._assignment_response(versioned.manifest, physical_ir)

    async def read_source(
        self,
        *,
        assignment_id: str,
        owner_cookie: str | None,
        range_header: str | None,
        head_only: bool,
    ) -> Response:
        versioned, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        return await self._run_storage(
            partial(
                self._stored_pdf_response,
                reference=versioned.manifest.source,
                filename=versioned.manifest.source_filename,
                error_code="stale_source",
                range_header=range_header,
                head_only=head_only,
                disposition="inline",
            ),
            version=versioned.manifest.version,
        )

    async def get_page_context(
        self,
        *,
        assignment_id: str,
        page_number: int,
        question_id: str,
        preview: str,
        owner_cookie: str | None,
    ) -> PageContextResponse:
        versioned, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        manifest = versioned.manifest
        physical_ir = await self._run_storage(
            partial(self._load_ir, manifest), version=manifest.version
        )
        question = _find_question(manifest, question_id)
        if question.page_number != page_number:
            raise _not_found("question_not_found", "That question could not be found.")
        crop = _context_crop(physical_ir, question)
        source_url = f"/api/v2/assignments/{assignment_id}/source"
        source_sha256 = manifest.source.sha256
        source_status = SourceStatus.ORIGINAL
        if preview == "confirmed":
            completed = next(
                (
                    item
                    for item in reversed(manifest.exports)
                    if item.status == DomainExportStatus.COMPLETE
                    and item.object_ref is not None
                    and item.assignment_version == manifest.version
                ),
                None,
            )
            if completed is not None and completed.object_ref is not None:
                source_url = (
                    f"/api/v2/assignments/{assignment_id}/exports/{completed.export_id}/download"
                )
                source_sha256 = completed.object_ref.sha256
                source_status = SourceStatus.COMPLETED_COPY_PREVIEW
        return PageContextResponse(
            version=manifest.version,
            question_id=question.question_id,
            question_index=question.index,
            page_number=question.page_number,
            source_status=source_status,
            source_url=source_url,
            source_sha256=source_sha256,
            crop=PageRect(
                x_mpt=crop.x0,
                y_mpt=crop.y0,
                width_mpt=crop.width,
                height_mpt=crop.height,
            ),
        )

    async def create_candidate(
        self,
        *,
        assignment_id: str,
        question_id: str,
        body: CandidateRequest,
        owner_cookie: str | None,
    ) -> CandidateResponse:
        observed, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        try:
            updated, candidate = replace_candidate(
                observed.manifest,
                question_id=question_id,
                assignment_version=body.assignment_version,
                exact_text=body.text,
                origin=DomainCandidateOrigin(body.origin.value),
                interaction=_domain_interaction(body),
                now=self._now(),
            )
            saved = await self._run_storage(
                partial(self._save, observed, updated),
                version=observed.manifest.version,
                mutation=True,
            )
        except DomainError as error:
            raise _domain_api_error(error) from error
        return CandidateResponse(
            version=saved.manifest.version,
            candidate=_candidate_response(question_id, candidate),
        )

    async def request_rephrase(
        self,
        *,
        assignment_id: str,
        question_id: str,
        body: RephraseRequest,
        owner_cookie: str | None,
    ) -> RephraseResponse:
        observed, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        manifest = observed.manifest
        if body.assignment_version != manifest.version:
            raise _conflict(
                "assignment_version_conflict",
                "The assignment changed. Reload it and try again.",
                manifest.version,
            )
        question = _find_question(manifest, question_id)
        candidate = question.current_candidate
        if (
            candidate is None
            or candidate.candidate_id != body.candidate_id
            or candidate.candidate_version != body.candidate_version
        ):
            raise _conflict(
                "candidate_not_found",
                "That answer changed. Review the current answer and try again.",
                manifest.version,
            )
        raise ClarosError(
            code="provider_unavailable",
            message="Suggested wording is temporarily unavailable. Keep your wording or try again.",
            recoverable=True,
            status_code=503,
            version=manifest.version,
        )

    async def create_review(
        self,
        *,
        assignment_id: str,
        question_id: str,
        body: ReviewRequest,
        owner_cookie: str | None,
    ) -> ReviewResponse:
        observed, session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        manifest = observed.manifest
        physical_ir = await self._run_storage(
            partial(self._load_ir, manifest), version=manifest.version
        )
        question = _find_question(manifest, question_id)
        candidate = question.current_candidate
        if (
            candidate is None
            or candidate.candidate_id != body.candidate_id
            or candidate.candidate_version != body.candidate_version
        ):
            raise _conflict(
                "candidate_not_found",
                "That answer changed. Review the current answer and try again.",
                manifest.version,
            )
        try:
            plan = _canonical_review_plan(
                physical_ir,
                manifest,
                question_id=question_id,
                exact_text=candidate.exact_text,
            )
            if plan.outcome == "reject":
                raise InvalidCandidate("This answer could not be placed safely.")
            placement = DomainPlacement(plan.outcome)
            result = issue_review(
                manifest,
                owner_hash=owner_hash(
                    session.owner_id, self.settings.cookie_secret.get_secret_value()
                ),
                question_id=question_id,
                candidate_id=body.candidate_id,
                candidate_version=body.candidate_version,
                assignment_version=body.assignment_version,
                placement=placement,
                placement_hash=plan.placement_hash,
                token_secret=self.settings.review_token_secret.get_secret_value(),
                now=self._now(),
                ttl_seconds=self.settings.review_ttl_seconds,
            )
            saved = await self._run_storage(
                partial(self._save, observed, result.manifest),
                version=manifest.version,
                mutation=True,
            )
        except DocumentEngineError as error:
            raise _document_api_error(error) from error
        except DomainError as error:
            raise _domain_api_error(error) from error
        return ReviewResponse(
            version=saved.manifest.version,
            review_token=result.review_token,
            expires_at=result.record.expires_at,
            question_id=question_id,
            candidate=_candidate_response(question_id, candidate),
            attribution=StudentAttribution(candidate.attribution.value),
            placement=Placement(placement.value),
            preview_context_url=(
                f"/api/v2/assignments/{assignment_id}/pages/{question.page_number}"
                f"/context?question_id={quote(question_id)}"
            ),
        )

    async def confirm_answer(
        self,
        *,
        assignment_id: str,
        question_id: str,
        body: ConfirmRequest,
        owner_cookie: str | None,
    ) -> ConfirmResponse:
        observed, session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        owner_digest = owner_hash(session.owner_id, self.settings.cookie_secret.get_secret_value())

        def apply(current: VersionedManifest) -> Any:
            return confirm_candidate(
                current.manifest,
                owner_hash=owner_digest,
                question_id=question_id,
                review_token=body.review_token,
                candidate_id=body.candidate_id,
                candidate_version=body.candidate_version,
                assignment_version=body.assignment_version,
                token_secret=self.settings.review_token_secret.get_secret_value(),
                now=self._now(),
            )

        def validate_current_placement(current: VersionedManifest, result: Any) -> None:
            if result.replayed:
                return
            physical_ir = self._load_ir(current.manifest)
            question = _find_question(current.manifest, question_id)
            candidate = question.current_candidate
            if candidate is None:
                raise _conflict(
                    "candidate_not_found",
                    "That answer changed. Review the current answer and try again.",
                    current.manifest.version,
                )
            current_plan = _canonical_review_plan(
                physical_ir,
                current.manifest,
                question_id=question_id,
                exact_text=candidate.exact_text,
            )
            if not hmac.compare_digest(
                current_plan.placement_hash,
                result.confirmed_answer.placement_hash,
            ):
                raise ClarosError(
                    code="placement_changed",
                    message=_SAFE_EXPORT_FAILURES["placement_changed"],
                    recoverable=True,
                    status_code=409,
                    version=current.manifest.version,
                )

        try:
            result = apply(observed)
            await self._run_storage(
                partial(validate_current_placement, observed, result),
                version=observed.manifest.version,
            )
            if not result.replayed:
                try:
                    await self._run_storage(
                        partial(self._save, observed, result.manifest),
                        version=observed.manifest.version,
                        mutation=True,
                    )
                except ClarosError as conflict:
                    if conflict.code != "assignment_version_conflict":
                        raise
                    latest, _session = await self._run_storage(
                        partial(self._load_owned, assignment_id, owner_cookie)
                    )
                    result = apply(latest)
                    await self._run_storage(
                        partial(validate_current_placement, latest, result),
                        version=latest.manifest.version,
                    )
                    if not result.replayed:
                        raise conflict
        except DomainError as error:
            raise _domain_api_error(error) from error
        return ConfirmResponse(
            version=result.version,
            confirmation_id=result.confirmed_answer.confirmation_id,
            confirmed_answer=_confirmed_response(question_id, result.confirmed_answer),
            replayed=result.replayed,
        )

    async def begin_revision(
        self,
        *,
        assignment_id: str,
        question_id: str,
        body: BeginRevisionRequest,
        owner_cookie: str | None,
    ) -> BeginRevisionResponse:
        observed, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        question = _find_question(observed.manifest, question_id)
        prior = question.confirmed_answer
        if prior is None:
            raise _conflict(
                "candidate_not_found",
                "There is no confirmed answer to revise.",
                observed.manifest.version,
            )
        try:
            updated, revision = begin_revision(
                observed.manifest,
                question_id=question_id,
                assignment_version=body.assignment_version,
                now=self._now(),
            )
            saved = await self._run_storage(
                partial(self._save, observed, updated),
                version=observed.manifest.version,
                mutation=True,
            )
        except DomainError as error:
            raise _domain_api_error(error) from error
        return BeginRevisionResponse(
            version=saved.manifest.version,
            question_id=question_id,
            edit_seed=revision.edit_seed,
            prior_confirmed_answer=_confirmed_response(question_id, prior),
        )

    async def create_export(
        self,
        *,
        assignment_id: str,
        body: CreateExportRequest,
        owner_cookie: str | None,
    ) -> tuple[ExportResponse, bool]:
        budget = _RequestBudget.start(self._request_timeout_seconds, self._monotonic)
        observed, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie),
            timeout_seconds=budget.remaining(self._storage_timeout_seconds),
        )
        try:
            started = start_export(
                observed.manifest,
                assignment_version=body.assignment_version,
                idempotency_key=body.idempotency_key,
                now=self._now(),
                stale_after_seconds=self.settings.request_timeout_seconds,
            )
            if started.replayed and started.manifest == observed.manifest:
                return self._export_response(started.manifest, started.export), True
            active = await self._run_storage(
                partial(self._save, observed, started.manifest),
                version=observed.manifest.version,
                timeout_seconds=budget.remaining(self._storage_timeout_seconds),
                mutation=True,
            )
        except DomainError as error:
            raise _domain_api_error(error) from error
        except _RequestBudgetExpired as error:
            raise ClarosError(
                code="export_timeout",
                message="The completed PDF took too long to prepare. Try again.",
                recoverable=True,
                status_code=503,
                version=observed.manifest.version,
            ) from error

        created_publications: list[ObjectMetadata] = []
        try:
            try:
                source = await self._run_storage(
                    partial(self.store.read, active.manifest.source.key),
                    version=active.manifest.version,
                    timeout_seconds=budget.remaining(self._storage_timeout_seconds),
                )
            except (ObjectNotFound, ObjectIntegrityError, GenerationConflict) as error:
                raise ClarosError(
                    code="stale_source",
                    message=_SAFE_EXPORT_FAILURES["stale_source"],
                    recoverable=True,
                    status_code=409,
                    version=active.manifest.version,
                ) from error
            _require_matching_object(
                active.manifest.source,
                source.metadata,
                code="stale_source",
                version=active.manifest.version,
            )
            physical_ir = await self._run_storage(
                partial(self._load_ir, active.manifest),
                version=active.manifest.version,
                timeout_seconds=budget.remaining(self._storage_timeout_seconds),
            )
            answers = tuple(
                DocumentAnswer(
                    question_id=item.question_id,
                    display_identifier=_find_question(
                        active.manifest, item.question_id
                    ).display_identifier,
                    prompt_block_ids=_find_question(
                        active.manifest, item.question_id
                    ).prompt_block_ids,
                    context_block_ids=_find_question(
                        active.manifest, item.question_id
                    ).context_block_ids,
                    exact_text=item.answer.exact_text,
                    reviewed_placement_hash=item.answer.placement_hash,
                )
                for item in confirmed_answers_for_export(active.manifest)
            )
            artifact = await self.document_executor.export(
                source.data,
                physical_ir,
                active.manifest.title,
                answers,
                timeout_seconds=budget.remaining(self._document_timeout_seconds),
            )
            pdf_metadata, pdf_created = await self._run_storage(
                partial(
                    self._create_or_verify,
                    export_pdf_object_key(assignment_id, started.export.export_id),
                    artifact.pdf_bytes,
                    content_type="application/pdf",
                ),
                version=active.manifest.version,
                timeout_seconds=budget.remaining(self._storage_timeout_seconds),
                mutation=True,
            )
            if pdf_created:
                created_publications.append(pdf_metadata)
            manifest_metadata, manifest_created = await self._run_storage(
                partial(
                    self._create_or_verify,
                    export_manifest_object_key(assignment_id, started.export.export_id),
                    artifact.manifest_bytes,
                    content_type="application/json; charset=utf-8",
                ),
                version=active.manifest.version,
                timeout_seconds=budget.remaining(self._storage_timeout_seconds),
                mutation=True,
            )
            if manifest_created:
                created_publications.append(manifest_metadata)
            saved, completed = await self._run_storage(
                partial(
                    self._complete_published_export,
                    active,
                    export_id=started.export.export_id,
                    object_ref=_object_reference(pdf_metadata),
                    manifest_ref=_object_reference(manifest_metadata),
                ),
                version=active.manifest.version,
                timeout_seconds=budget.remaining(self._storage_timeout_seconds),
                mutation=True,
            )
            return self._export_response(saved.manifest, completed), started.replayed
        except (DocumentExecutionTimeout, _RequestBudgetExpired) as error:
            failed = await self._record_export_failure(
                active,
                started.export.export_id,
                "publish_failed",
                budget=budget,
            )
            if failed:
                await self._cleanup_publications_async(created_publications, budget=budget)
            raise ClarosError(
                code="export_timeout",
                message="The completed PDF took too long to prepare. Try again.",
                recoverable=True,
                status_code=503,
                version=active.manifest.version,
            ) from error
        except DocumentEngineError as error:
            failed = await self._record_export_failure(
                active,
                started.export.export_id,
                error.code,
                budget=budget,
            )
            if failed:
                await self._cleanup_publications_async(created_publications, budget=budget)
            raise _document_api_error(error) from error
        except Exception as error:
            failed = await self._record_export_failure(
                active,
                started.export.export_id,
                "publish_failed",
                budget=budget,
            )
            if failed:
                await self._cleanup_publications_async(created_publications, budget=budget)
            if isinstance(error, ClarosError):
                raise
            raise ClarosError(
                code="publish_failed",
                message=_SAFE_EXPORT_FAILURES["publish_failed"],
                recoverable=True,
                status_code=503,
                version=active.manifest.version,
            ) from error

    async def get_export(
        self,
        *,
        assignment_id: str,
        export_id: str,
        owner_cookie: str | None,
    ) -> ExportResponse:
        versioned, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        export = _find_export(versioned.manifest, export_id)
        return self._export_response(versioned.manifest, export)

    async def read_export(
        self,
        *,
        assignment_id: str,
        export_id: str,
        owner_cookie: str | None,
        range_header: str | None,
        head_only: bool,
    ) -> Response:
        versioned, _session = await self._run_storage(
            partial(self._load_owned, assignment_id, owner_cookie)
        )
        export = _find_export(versioned.manifest, export_id)
        if export.status != DomainExportStatus.COMPLETE or export.object_ref is None:
            raise _conflict(
                "export_not_ready",
                "The completed PDF is not ready yet.",
                versioned.manifest.version,
            )
        return await self._run_storage(
            partial(
                self._stored_pdf_response,
                reference=export.object_ref,
                filename=_completed_filename(versioned.manifest.source_filename),
                error_code="invalid_export",
                range_header=range_header,
                head_only=head_only,
                disposition="attachment",
            ),
            version=versioned.manifest.version,
        )

    async def issue_realtime_credential(
        self,
        *,
        body: RealtimeCredentialRequest,
        owner_cookie: str | None,
    ) -> RealtimeCredentialResponse:
        versioned, session = await self._run_storage(
            partial(self._load_owned, body.assignment_id, owner_cookie)
        )
        self._check_rate_limit(
            scope="realtime",
            subject=session.owner_id,
            limit=self.settings.realtime_rate_limit,
            window_seconds=self.settings.realtime_rate_window_seconds,
        )
        if body.assignment_version != versioned.manifest.version:
            raise _conflict(
                "assignment_version_conflict",
                "The assignment changed. Reload it and try again.",
                versioned.manifest.version,
            )
        _find_question(versioned.manifest, body.question_id)
        raise ClarosError(
            code="provider_unavailable",
            message="Voice is unavailable right now. Continue by typing.",
            recoverable=True,
            status_code=503,
            version=versioned.manifest.version,
        )

    async def _run_storage(
        self,
        operation: Callable[[], _T],
        *,
        version: int | None = None,
        timeout_seconds: float | None = None,
        mutation: bool = False,
    ) -> _T:
        deadline = self._storage_timeout_seconds if timeout_seconds is None else timeout_seconds
        if deadline <= 0:
            raise ValueError("storage deadline must be positive")
        try:
            future = asyncio.get_running_loop().run_in_executor(_STORAGE_EXECUTOR, operation)
            try:
                with anyio.fail_after(deadline):
                    return await asyncio.shield(future)
            except TimeoutError:
                if mutation:
                    # Threads cannot be cancelled safely. A timed-out mutation
                    # must settle before the request returns so it cannot later
                    # publish an object or manifest the caller never observed.
                    return await asyncio.shield(future)
                raise
        except (TimeoutError, GoogleDeadlineExceeded) as error:
            raise ClarosError(
                code="storage_timeout",
                message=_STORAGE_TIMEOUT_MESSAGE,
                recoverable=True,
                status_code=503,
                version=version,
            ) from error
        except StorageError as error:
            raise ClarosError(
                code="storage_unavailable",
                message="Worksheet storage is temporarily unavailable. Try again.",
                recoverable=True,
                status_code=503,
                version=version,
            ) from error

    def _create_analyzing_assignment(
        self,
        *,
        assignment_id: str,
        source_bytes: bytes,
        source_filename: str,
        owner_digest: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> VersionedManifest:
        source_metadata = self.store.create(
            source_object_key(assignment_id),
            source_bytes,
            content_type="application/pdf",
        )
        try:
            manifest = AssignmentManifest(
                assignment_id=assignment_id,
                owner_hash=owner_digest,
                version=1,
                status=DomainAssignmentStatus.ANALYZING,
                title=Path(source_filename).stem[:255] or "Worksheet",
                source_filename=source_filename,
                source=_object_reference(source_metadata),
                physical_ir=None,
                questions=(),
                warnings=(),
                created_at=created_at,
                expires_at=expires_at,
            )
            return self.manifests.create(manifest)
        except Exception:
            with suppress(Exception):
                self.store.delete(
                    source_metadata.key,
                    expected_generation=source_metadata.generation,
                )
            raise

    def _finish_analysis(
        self,
        observed: VersionedManifest,
        physical_ir: PhysicalDocumentIR,
        questions: tuple[QuestionState, ...],
    ) -> VersionedManifest:
        ir_metadata = self.store.create(
            physical_ir_object_key(observed.manifest.assignment_id),
            physical_ir.canonical_bytes(),
            content_type="application/json; charset=utf-8",
        )
        try:
            ready = observed.manifest.model_copy(
                update={
                    "status": DomainAssignmentStatus.READY,
                    "physical_ir": _object_reference(ir_metadata),
                    "questions": questions,
                    "warnings": tuple(physical_ir.ambiguity_flags),
                    "failure_code": None,
                }
            )
            return self._save(observed, ready)
        except Exception:
            with suppress(Exception):
                self.store.delete(ir_metadata.key, expected_generation=ir_metadata.generation)
            raise

    async def _record_analysis_failure(
        self,
        observed: VersionedManifest,
        code: str,
        *,
        budget: _RequestBudget | None = None,
    ) -> VersionedManifest:
        try:
            return await self._run_storage(
                partial(self._mark_analysis_failed, observed, code),
                version=observed.manifest.version,
                timeout_seconds=(
                    budget.remaining(self._storage_timeout_seconds, recovery=True)
                    if budget is not None
                    else None
                ),
                mutation=True,
            )
        except (ClarosError, _RequestBudgetExpired):
            return observed

    def _mark_analysis_failed(self, observed: VersionedManifest, code: str) -> VersionedManifest:
        current = observed
        for _attempt in range(4):
            if current.manifest.status != DomainAssignmentStatus.ANALYZING:
                return current
            failed = current.manifest.model_copy(
                update={
                    "status": DomainAssignmentStatus.ANALYSIS_FAILED,
                    "failure_code": code,
                    "questions": (),
                }
            )
            try:
                return self._save(current, failed)
            except ClarosError as error:
                if error.code != "assignment_version_conflict":
                    raise
                current = self.manifests.load(current.manifest.assignment_id)
        return current

    async def _recover_stale_analysis(self, observed: VersionedManifest) -> VersionedManifest:
        if observed.manifest.status != DomainAssignmentStatus.ANALYZING:
            return observed
        age = (self._now().astimezone(UTC) - observed.manifest.created_at).total_seconds()
        if age < self._document_timeout_seconds:
            return observed
        return await self._run_storage(
            partial(self._mark_analysis_failed, observed, "analysis_timeout"),
            version=observed.manifest.version,
            mutation=True,
        )

    def _owner_for_creation(self, owner_cookie: str | None) -> tuple[OwnerSession, str]:
        secret = self.settings.cookie_secret.get_secret_value()
        if owner_cookie:
            try:
                existing = verify_owner_session(owner_cookie, secret, now=self._now())
                return create_owner_session(
                    secret,
                    now=self._now(),
                    ttl_seconds=self.settings.assignment_ttl_seconds,
                    owner_id_factory=lambda: existing.owner_id,
                )
            except OwnerSessionError:
                pass
        return create_owner_session(
            secret,
            now=self._now(),
            ttl_seconds=self.settings.assignment_ttl_seconds,
        )

    def _load_owned(
        self, assignment_id: str, owner_cookie: str | None
    ) -> tuple[VersionedManifest, OwnerSession]:
        try:
            versioned = self.manifests.load(assignment_id)
            session = require_assignment_owner(
                cookie=owner_cookie,
                stored_owner_hash=versioned.manifest.owner_hash,
                secret=self.settings.cookie_secret.get_secret_value(),
                assignment_expires_at=versioned.manifest.expires_at,
                now=self._now(),
            )
            return versioned, session
        except (
            ObjectNotFound,
            ObjectIntegrityError,
            AssignmentAccessDenied,
            ValueError,
        ) as error:
            raise _not_found(
                "assignment_not_found",
                "This worksheet session is no longer available.",
            ) from error

    def _load_ir(self, manifest: AssignmentManifest) -> PhysicalDocumentIR:
        if manifest.physical_ir is None:
            raise ClarosError(
                code="analysis_unavailable",
                message="The worksheet analysis is unavailable.",
                recoverable=True,
                status_code=409,
                version=manifest.version,
            )
        try:
            stored = self.store.read(manifest.physical_ir.key)
        except (ObjectNotFound, ObjectIntegrityError, GenerationConflict) as error:
            raise ClarosError(
                code="stale_physical_ir",
                message=_SAFE_EXPORT_FAILURES["stale_physical_ir"],
                recoverable=True,
                status_code=409,
                version=manifest.version,
            ) from error
        _require_matching_object(
            manifest.physical_ir,
            stored.metadata,
            code="stale_physical_ir",
            version=manifest.version,
        )
        try:
            physical_ir = parse_physical_ir(stored.data)
        except DocumentEngineError as error:
            raise _document_api_error(error, version=manifest.version) from error
        if not hmac.compare_digest(physical_ir.source_sha256, manifest.source.sha256):
            raise ClarosError(
                code="stale_physical_ir",
                message="The worksheet analysis changed. Review the answer again.",
                recoverable=True,
                status_code=409,
                version=manifest.version,
            )
        return physical_ir

    def _save(self, observed: VersionedManifest, updated: AssignmentManifest) -> VersionedManifest:
        try:
            return self.manifests.compare_and_swap(observed, updated)
        except GenerationConflict as error:
            try:
                current = self.manifests.load(observed.manifest.assignment_id)
                version = current.manifest.version
            except ObjectNotFound:
                version = observed.manifest.version
            raise _conflict(
                "assignment_version_conflict",
                "The assignment changed. Reload it and try again.",
                version,
            ) from error

    def _assignment_response(
        self, manifest: AssignmentManifest, physical_ir: PhysicalDocumentIR | None
    ) -> AssignmentResponse:
        questions = [_question_projection(question) for question in manifest.questions]
        inline = sum(
            question.placement_capability == DomainPlacementCapability.INLINE_POSSIBLE
            for question in manifest.questions
        )
        return AssignmentResponse(
            assignment_id=manifest.assignment_id,
            version=manifest.version,
            status=AssignmentStatus(manifest.status.value),
            title=manifest.title,
            source=SourceDocument(
                filename=manifest.source_filename,
                size_bytes=manifest.source.size_bytes,
                sha256=manifest.source.sha256,
                page_count=len(physical_ir.pages) if physical_ir is not None else None,
            ),
            question_count=len(questions),
            placement_summary=PlacementSummary(
                inline_possible=inline,
                appendix_only=len(questions) - inline,
            ),
            warnings=self._assignment_warnings(manifest, inline=inline),
            questions=questions,
        )

    @staticmethod
    def _assignment_warnings(manifest: AssignmentManifest, *, inline: int) -> list[SafeWarning]:
        if manifest.status == DomainAssignmentStatus.ANALYSIS_FAILED:
            code = manifest.failure_code or "analysis_failed"
            message = DOCUMENT_SAFE_MESSAGES.get(
                code,
                "Claros could not safely check this worksheet. Try another PDF.",
            )
            if code == "analysis_timeout":
                message = "Worksheet checking took too long. Try again."
            return [SafeWarning(code=code, message=message)]
        if inline < len(manifest.questions):
            return [
                SafeWarning(
                    code="appendix_conservative",
                    message=(
                        "Some answers will use an attached answer page when inline "
                        "placement cannot be proven safe."
                    ),
                )
            ]
        return []

    def _stored_pdf_response(
        self,
        *,
        reference: ObjectReference,
        filename: str,
        error_code: str,
        range_header: str | None,
        head_only: bool,
        disposition: str,
    ) -> Response:
        if range_header is None:
            try:
                stored = self.store.read(reference.key)
            except (ObjectNotFound, ObjectIntegrityError, GenerationConflict) as error:
                raise ClarosError(
                    code=error_code,
                    message=_SAFE_EXPORT_FAILURES[error_code],
                    recoverable=True,
                    status_code=409,
                ) from error
            _require_matching_object(reference, stored.metadata, code=error_code)
            return self._binary_response(
                data=stored.data,
                metadata=stored.metadata,
                filename=filename,
                byte_range=None,
                head_only=head_only,
                disposition=disposition,
            )
        try:
            byte_range = parse_byte_range(range_header, reference.size_bytes)
        except RangeNotSatisfiable:
            headers = self._pdf_headers(
                metadata=ObjectMetadata(
                    key=reference.key,
                    generation=reference.generation,
                    size=reference.size_bytes,
                    content_type=reference.content_type,
                    sha256=reference.sha256,
                ),
                filename=filename,
                disposition=disposition,
            )
            return JSONResponse(
                status_code=416,
                content={
                    "error": {
                        "code": "range_not_satisfiable",
                        "message": "That PDF byte range is unavailable.",
                        "recoverable": True,
                    }
                },
                headers={**headers, "Content-Range": f"bytes */{reference.size_bytes}"},
            )
        try:
            stored = self.store.read_range(reference.key, byte_range)
        except (ObjectNotFound, ObjectIntegrityError, GenerationConflict) as error:
            raise ClarosError(
                code=error_code,
                message=_SAFE_EXPORT_FAILURES[error_code],
                recoverable=True,
                status_code=409,
            ) from error
        _require_matching_object(reference, stored.metadata, code=error_code)
        return self._binary_response(
            data=stored.data,
            metadata=stored.metadata,
            filename=filename,
            byte_range=byte_range,
            head_only=head_only,
            disposition=disposition,
        )

    @staticmethod
    def _pdf_headers(
        *, metadata: ObjectMetadata, filename: str, disposition: str
    ) -> dict[str, str]:
        return {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
            "Content-Disposition": (f"{disposition}; filename*=UTF-8''{quote(filename, safe='')}"),
            "ETag": f'"sha256-{metadata.sha256}-g{metadata.generation}"',
        }

    def _binary_response(
        self,
        *,
        data: bytes,
        metadata: ObjectMetadata,
        filename: str,
        byte_range: Any | None,
        head_only: bool,
        disposition: str,
    ) -> Response:
        headers = self._pdf_headers(metadata=metadata, filename=filename, disposition=disposition)
        if byte_range is None:
            headers["Content-Length"] = str(len(data))
            return Response(
                content=b"" if head_only else data,
                media_type="application/pdf",
                headers=headers,
            )
        headers.update(
            {
                "Content-Length": str(len(data)),
                "Content-Range": byte_range.content_range,
            }
        )
        return Response(
            content=b"" if head_only else data,
            status_code=206,
            media_type="application/pdf",
            headers=headers,
        )

    def _create_or_verify(
        self, key: str, data: bytes, *, content_type: str
    ) -> tuple[ObjectMetadata, bool]:
        try:
            return self.store.create(key, data, content_type=content_type), True
        except ObjectAlreadyExists as error:
            stored = self.store.read(key)
            digest = hashlib.sha256(data).hexdigest()
            if stored.data != data or not hmac.compare_digest(stored.metadata.sha256, digest):
                raise ClarosError(
                    code="publish_failed",
                    message=_SAFE_EXPORT_FAILURES["publish_failed"],
                    recoverable=True,
                    status_code=503,
                ) from error
            return stored.metadata, False

    def _complete_published_export(
        self,
        observed: VersionedManifest,
        *,
        export_id: str,
        object_ref: ObjectReference,
        manifest_ref: ObjectReference,
    ) -> tuple[VersionedManifest, Any]:
        current = observed
        for _attempt in range(4):
            existing = _find_export(current.manifest, export_id)
            if existing.status == DomainExportStatus.COMPLETE:
                if existing.object_ref == object_ref and existing.manifest_ref == manifest_ref:
                    return current, existing
                raise ClarosError(
                    code="invalid_export",
                    message=_SAFE_EXPORT_FAILURES["invalid_export"],
                    recoverable=True,
                    status_code=409,
                    version=current.manifest.version,
                )
            if existing.status != DomainExportStatus.CREATING:
                raise ClarosError(
                    code="publish_failed",
                    message=_SAFE_EXPORT_FAILURES["publish_failed"],
                    recoverable=True,
                    status_code=409,
                    version=current.manifest.version,
                )
            completed_manifest, completed = complete_export(
                current.manifest,
                export_id=export_id,
                object_ref=object_ref,
                manifest_ref=manifest_ref,
            )
            try:
                return self._save(current, completed_manifest), completed
            except ClarosError as error:
                if error.code != "assignment_version_conflict":
                    raise
                current = self.manifests.load(current.manifest.assignment_id)
        raise ClarosError(
            code="publish_failed",
            message=_SAFE_EXPORT_FAILURES["publish_failed"],
            recoverable=True,
            status_code=503,
            version=current.manifest.version,
        )

    def _cleanup_publications(self, publications: list[ObjectMetadata]) -> None:
        for metadata in reversed(publications):
            with suppress(ObjectNotFound, ObjectIntegrityError, GenerationConflict):
                self.store.delete(metadata.key, expected_generation=metadata.generation)

    async def _cleanup_publications_async(
        self,
        publications: list[ObjectMetadata],
        *,
        budget: _RequestBudget | None = None,
    ) -> None:
        if not publications:
            return
        with suppress(ClarosError, _RequestBudgetExpired):
            await self._run_storage(
                partial(self._cleanup_publications, publications),
                timeout_seconds=(
                    budget.remaining(self._storage_timeout_seconds, recovery=True)
                    if budget is not None
                    else None
                ),
                mutation=True,
            )

    async def _record_export_failure(
        self,
        observed: VersionedManifest,
        export_id: str,
        code: str,
        *,
        budget: _RequestBudget | None = None,
    ) -> bool:
        current = observed
        for _attempt in range(4):
            try:
                export = _find_export(current.manifest, export_id)
                if export.status == DomainExportStatus.COMPLETE:
                    return False
                updated, _export = fail_export(
                    current.manifest, export_id=export_id, failure_code=code
                )
                await self._run_storage(
                    partial(self._save, current, updated),
                    version=current.manifest.version,
                    timeout_seconds=(
                        budget.remaining(self._storage_timeout_seconds, recovery=True)
                        if budget is not None
                        else None
                    ),
                    mutation=True,
                )
                return True
            except ClarosError as error:
                if error.code != "assignment_version_conflict":
                    return False
                try:
                    current = await self._run_storage(
                        partial(self.manifests.load, current.manifest.assignment_id),
                        version=current.manifest.version,
                        timeout_seconds=(
                            budget.remaining(self._storage_timeout_seconds, recovery=True)
                            if budget is not None
                            else None
                        ),
                    )
                except (ObjectNotFound, ObjectIntegrityError, _RequestBudgetExpired):
                    return False
            except (LookupError, ValueError, _RequestBudgetExpired):
                return False
        return False

    def _export_response(self, manifest: AssignmentManifest, export: Any) -> ExportResponse:
        complete = export.status == DomainExportStatus.COMPLETE
        return ExportResponse(
            version=manifest.version,
            export_id=export.export_id,
            assignment_version=export.assignment_version,
            status=ExportStatus(export.status.value),
            filename=_completed_filename(manifest.source_filename),
            size_bytes=export.object_ref.size_bytes if complete else None,
            download_url=(
                f"/api/v2/assignments/{manifest.assignment_id}/exports/{export.export_id}/download"
                if complete
                else None
            ),
            failure=(
                ExportFailure(
                    code=export.failure_code,
                    message=_SAFE_EXPORT_FAILURES.get(
                        export.failure_code,
                        "The completed PDF could not be prepared. Try again.",
                    ),
                    recoverable=True,
                )
                if export.status == DomainExportStatus.FAILED and export.failure_code is not None
                else None
            ),
        )

    def _check_rate_limit(
        self,
        *,
        scope: str,
        subject: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        try:
            self.rate_limiter.check(
                scope=scope,
                subject=subject,
                limit=limit,
                window_seconds=window_seconds,
            )
        except RateLimitExceeded as error:
            raise ClarosError(
                code="rate_limit_exceeded",
                message="Too many requests. Wait a moment and try again.",
                recoverable=True,
                status_code=429,
            ) from error


def build_assignment_service(settings: Settings) -> AssignmentApplicationService:
    store: ObjectStore
    if settings.storage_backend == "gcs":
        store = GCSObjectStore(cast(str, settings.gcs_bucket))
    else:
        store = LocalObjectStore(settings.local_storage_path)
    current_engine = DocumentProcessExecutor()
    document_executor = select_pdf_engine(
        current_engine,
        engine=settings.pdf_engine,
        runtime=OpenPdfRuntime(
            jar_path=settings.openpdf_jar_path,
            font_root=settings.openpdf_font_root,
            qpdf_path=settings.openpdf_qpdf_path,
            java_command=settings.openpdf_java_command,
            max_input_bytes=settings.max_upload_bytes,
            max_output_bytes=settings.openpdf_max_output_bytes,
            max_pages=settings.max_pages,
            jvm_heap_mib=settings.openpdf_jvm_heap_mib,
        ),
    )
    return AssignmentApplicationService(
        settings=settings,
        store=store,
        document_executor=document_executor,  # type: ignore[arg-type]
    )


def _question_evidence(question: QuestionState) -> QuestionEvidence:
    return QuestionEvidence(
        question_id=question.question_id,
        display_identifier=question.display_identifier,
        prompt_block_ids=question.prompt_block_ids,
        context_block_ids=question.context_block_ids,
    )


def _canonical_review_plan(
    physical_ir: PhysicalDocumentIR,
    manifest: AssignmentManifest,
    *,
    question_id: str,
    exact_text: str,
) -> Any:
    """Plan in source order while preserving every previously reviewed placement."""

    def compute(force_current_appendix: bool) -> tuple[Any, bool]:
        plans: list[Any] = []
        current_plan = None
        mismatch = False
        for question in manifest.questions:
            is_current = question.question_id == question_id
            answer = question.confirmed_answer
            if not is_current and answer is None:
                continue
            answer_text = exact_text if is_current else answer.exact_text
            plan = resolve_placement(
                physical_ir,
                _question_evidence(question),
                answer_text,
                occupied_plans=tuple(plans),
                force_appendix=force_current_appendix and is_current,
            )
            if not is_current and not hmac.compare_digest(
                plan.placement_hash, answer.placement_hash
            ):
                forced = resolve_placement(
                    physical_ir,
                    _question_evidence(question),
                    answer_text,
                    occupied_plans=tuple(plans),
                    force_appendix=True,
                )
                if hmac.compare_digest(forced.placement_hash, answer.placement_hash):
                    plan = forced
                else:
                    mismatch = True
            plans.append(plan)
            if is_current:
                current_plan = plan
        if current_plan is None:
            raise _not_found("question_not_found", "That question could not be found.")
        return current_plan, mismatch

    current_plan, mismatch = compute(False)
    if mismatch and current_plan.outcome == "inline":
        current_plan, mismatch = compute(True)
    if mismatch:
        raise ClarosError(
            code="placement_changed",
            message=_SAFE_EXPORT_FAILURES["placement_changed"],
            recoverable=True,
            status_code=409,
            version=manifest.version,
        )
    return current_plan


def _context_crop(physical_ir: PhysicalDocumentIR, question: QuestionState) -> CanonicalBox:
    page = physical_ir.pages[question.page_number - 1]
    blocks = tuple(physical_ir.block_by_id(item) for item in question.prompt_block_ids)
    prompt = CanonicalBox.union(tuple(block.bbox for block in blocks))
    horizontal_padding = 24_000
    above = 24_000
    below = 180_000
    return CanonicalBox(
        x0=max(0, prompt.x0 - horizontal_padding),
        y0=max(0, prompt.y0 - above),
        x1=min(page.width_mpt, prompt.x1 + horizontal_padding),
        y1=min(page.height_mpt, max(prompt.y1 + below, prompt.y0 + 120_000)),
    )


def _domain_interaction(body: CandidateRequest) -> Any:
    interaction = body.interaction
    if isinstance(interaction, DirectTypedInteraction):
        return DomainDirectTypedInteraction()
    if isinstance(interaction, DirectVoiceInteraction):
        return DomainDirectVoiceInteraction(
            realtime_session_id=interaction.realtime_session_id,
            source_turn_ids=tuple(interaction.source_turn_ids),
            normalization=interaction.normalization,
        )
    if isinstance(interaction, GuidedFinalInteraction):
        return DomainGuidedFinalInteraction(
            realtime_session_id=interaction.realtime_session_id,
            source_turn_ids=tuple(interaction.source_turn_ids),
            input=interaction.input,
        )
    if isinstance(interaction, StudentEditInteraction):
        return DomainStudentEditInteraction(
            prior_candidate_id=interaction.prior_candidate_id,
            prior_candidate_version=interaction.prior_candidate_version,
        )
    if isinstance(interaction, SelectedRephraseInteraction):
        return DomainSelectedRephraseInteraction(
            rephrase_id=interaction.rephrase_id,
            suggestion_candidate_id=interaction.suggestion_candidate_id,
        )
    raise TypeError("unsupported candidate interaction")


def _candidate_response(question_id: str, candidate: Any) -> Candidate:
    return Candidate(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        question_id=question_id,
        text=candidate.exact_text,
        origin=CandidateOrigin(candidate.origin.value),
        attribution=StudentAttribution(candidate.attribution.value),
        created_at=candidate.created_at,
    )


def _confirmed_response(question_id: str, answer: Any) -> ConfirmedAnswer:
    return ConfirmedAnswer(
        question_id=question_id,
        revision=answer.revision,
        candidate_id=answer.candidate_id,
        candidate_version=answer.candidate_version,
        exact_text=answer.exact_text,
        origin=CandidateOrigin(answer.origin.value),
        attribution=StudentAttribution(answer.attribution.value),
        placement=Placement(answer.placement.value),
        confirmed_at=answer.confirmed_at,
    )


def _question_projection(question: QuestionState) -> QuestionProjection:
    candidate = (
        _candidate_response(question.question_id, question.current_candidate)
        if question.current_candidate is not None
        else None
    )
    confirmed = (
        _confirmed_response(question.question_id, question.confirmed_answer)
        if question.confirmed_answer is not None
        else None
    )
    return QuestionProjection(
        question_id=question.question_id,
        index=question.index,
        prompt=question.exact_prompt,
        instruction=question.instruction,
        page_number=question.page_number,
        placement_capability=PlacementCapability(question.placement_capability.value),
        candidate=candidate,
        wording_comparison=None,
        confirmed_answer=confirmed,
    )


def _find_question(manifest: AssignmentManifest, question_id: str) -> QuestionState:
    for question in manifest.questions:
        if question.question_id == question_id:
            return question
    raise _not_found("question_not_found", "That question could not be found.")


def _find_export(manifest: AssignmentManifest, export_id: str) -> Any:
    for export in manifest.exports:
        if export.export_id == export_id:
            return export
    raise _not_found("export_not_found", "That completed PDF could not be found.")


def _not_found(code: str, message: str) -> ClarosError:
    return ClarosError(
        code=code,
        message=message,
        recoverable=False,
        status_code=404,
    )


def _conflict(code: str, message: str, version: int) -> ClarosError:
    return ClarosError(
        code=code,
        message=message,
        recoverable=True,
        status_code=409,
        version=version,
    )


def _domain_api_error(error: DomainError) -> ClarosError:
    if isinstance(error, AssignmentVersionConflict):
        return _conflict(error.code, str(error), error.current_version)
    status_code = 409
    if isinstance(error, (QuestionNotFound,)):
        status_code = 404
    elif isinstance(error, (InvalidCandidate, InvalidCandidateOrigin)):
        status_code = 422
    elif isinstance(
        error,
        (
            CandidateNotFound,
            NoConfirmedAnswers,
            ReviewTokenExpired,
            ReviewTokenInvalid,
            ReviewTokenStale,
        ),
    ):
        status_code = 409
    return ClarosError(
        code=error.code,
        message=str(error),
        recoverable=True,
        status_code=status_code,
    )


def _document_api_error(error: DocumentEngineError, *, version: int | None = None) -> ClarosError:
    status_code = 413 if error.code == "file_too_large" else 422
    if error.code in {"placement_changed", "stale_physical_ir", "stale_source"}:
        status_code = 409
    return ClarosError(
        code=error.code,
        message=error.safe_message,
        recoverable=error.recoverable,
        status_code=status_code,
        version=version,
    )
