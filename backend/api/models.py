"""Authoritative FastAPI transport models for the Claros V2 API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

MAX_CANDIDATE_UTF8_BYTES = 8192


class TransportModel(BaseModel):
    """Strict base model shared by every JSON request and response."""

    model_config = ConfigDict(extra="forbid", strict=True)


class CandidateOrigin(StrEnum):
    STUDENT_VERBATIM = "student_verbatim"
    STUDENT_NORMALIZED = "student_normalized"
    CLAROS_REPHRASE = "claros_rephrase"
    STUDENT_AFTER_GUIDANCE = "student_after_guidance"
    STUDENT_EDITED = "student_edited"


class StudentAttribution(StrEnum):
    YOUR_WORDS = "Your words"
    SUGGESTED_WORDING = "Suggested wording"


class AssignmentStatus(StrEnum):
    ANALYZING = "analyzing"
    READY = "ready"
    ANALYSIS_FAILED = "analysis_failed"


class ExportStatus(StrEnum):
    CREATING = "creating"
    COMPLETE = "complete"
    FAILED = "failed"


class Placement(StrEnum):
    INLINE = "inline"
    APPENDIX = "appendix"


class PlacementCapability(StrEnum):
    INLINE_POSSIBLE = "inline_possible"
    APPENDIX_ONLY = "appendix_only"


class SourceStatus(StrEnum):
    ORIGINAL = "original"
    COMPLETED_COPY_PREVIEW = "completed_copy_preview"


class RealtimeMode(StrEnum):
    DIRECT = "direct"
    GUIDED = "guided"


class ErrorDetail(TransportModel):
    code: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1, max_length=300)
    recoverable: bool


class ErrorEnvelope(TransportModel):
    error: ErrorDetail
    version: int | None = Field(default=None, ge=1)


class SafeWarning(TransportModel):
    code: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1, max_length=300)


class SourceDocument(TransportModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int | None = Field(default=None, ge=1, le=8)


class Candidate(TransportModel):
    candidate_id: str = Field(min_length=1, max_length=96)
    candidate_version: int = Field(ge=1)
    question_id: str = Field(min_length=1, max_length=96)
    text: str
    origin: CandidateOrigin
    attribution: StudentAttribution
    created_at: datetime


class ConfirmedAnswer(TransportModel):
    question_id: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)
    candidate_id: str = Field(min_length=1, max_length=96)
    candidate_version: int = Field(ge=1)
    exact_text: str
    origin: CandidateOrigin
    attribution: StudentAttribution
    placement: Placement
    confirmed_at: datetime


class WordingComparison(TransportModel):
    rephrase_id: str = Field(min_length=1, max_length=96)
    original: Candidate
    suggestion: Candidate
    selected_candidate_id: str | None = Field(default=None, min_length=1, max_length=96)


class QuestionProjection(TransportModel):
    question_id: str = Field(min_length=1, max_length=96)
    index: int = Field(ge=1, le=40)
    prompt: str = Field(min_length=1)
    instruction: str | None = None
    page_number: int = Field(ge=1, le=8)
    placement_capability: PlacementCapability
    candidate: Candidate | None = None
    wording_comparison: WordingComparison | None = None
    confirmed_answer: ConfirmedAnswer | None = None


class PlacementSummary(TransportModel):
    inline_possible: int = Field(ge=0, le=40)
    appendix_only: int = Field(ge=0, le=40)


class AssignmentResponse(TransportModel):
    assignment_id: str = Field(min_length=1, max_length=96)
    version: int = Field(ge=1)
    status: AssignmentStatus
    title: str = Field(min_length=1, max_length=255)
    source: SourceDocument
    question_count: int = Field(ge=0, le=40)
    placement_summary: PlacementSummary
    warnings: list[SafeWarning] = Field(default_factory=list, max_length=40)
    questions: list[QuestionProjection] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def validate_status_projection(self) -> AssignmentResponse:
        if self.status == AssignmentStatus.READY and self.source.page_count is None:
            raise ValueError("ready assignment requires a verified page count")
        if self.status != AssignmentStatus.READY and self.source.page_count is not None:
            raise ValueError("unfinished assignment cannot expose an unverified page count")
        return self


class PageRect(TransportModel):
    """Crop-box-relative, top-left rectangle in integer milli-points."""

    x_mpt: int = Field(ge=0)
    y_mpt: int = Field(ge=0)
    width_mpt: int = Field(gt=0)
    height_mpt: int = Field(gt=0)


class PageContextResponse(TransportModel):
    version: int = Field(ge=1)
    question_id: str = Field(min_length=1, max_length=96)
    question_index: int = Field(ge=1, le=40)
    page_number: int = Field(ge=1, le=8)
    source_status: SourceStatus
    source_url: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    crop: PageRect


class DirectTypedInteraction(TransportModel):
    kind: Literal["direct_typed"]


class DirectVoiceInteraction(TransportModel):
    kind: Literal["direct_voice"]
    realtime_session_id: str = Field(min_length=1, max_length=128)
    source_turn_ids: list[str] = Field(min_length=1, max_length=24)
    normalization: Literal["none", "punctuation_only"]


class GuidedFinalInteraction(TransportModel):
    kind: Literal["guided_final"]
    realtime_session_id: str = Field(min_length=1, max_length=128)
    source_turn_ids: list[str] = Field(min_length=1, max_length=24)
    input: Literal["typed", "voice"]


class StudentEditInteraction(TransportModel):
    kind: Literal["student_edit"]
    prior_candidate_id: str = Field(min_length=1, max_length=96)
    prior_candidate_version: int = Field(ge=1)


class SelectedRephraseInteraction(TransportModel):
    kind: Literal["selected_rephrase"]
    rephrase_id: str = Field(min_length=1, max_length=96)
    suggestion_candidate_id: str = Field(min_length=1, max_length=96)


CandidateInteraction = Annotated[
    DirectTypedInteraction
    | DirectVoiceInteraction
    | GuidedFinalInteraction
    | StudentEditInteraction
    | SelectedRephraseInteraction,
    Field(discriminator="kind"),
]


class CandidateRequest(TransportModel):
    assignment_version: int = Field(ge=1)
    text: str
    origin: CandidateOrigin
    interaction: CandidateInteraction

    @field_validator("origin", mode="before")
    @classmethod
    def parse_candidate_origin(cls, value: object) -> object:
        if type(value) is str:
            return CandidateOrigin(value)
        return value

    @field_validator("text")
    @classmethod
    def validate_exact_candidate_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("candidate text cannot contain a NUL character")
        if not value.strip():
            raise ValueError("candidate text cannot be blank")
        if len(value.encode("utf-8")) > MAX_CANDIDATE_UTF8_BYTES:
            raise ValueError(f"candidate text exceeds {MAX_CANDIDATE_UTF8_BYTES} UTF-8 bytes")
        return value


class CandidateResponse(TransportModel):
    version: int = Field(ge=1)
    candidate: Candidate


class RephraseRequest(TransportModel):
    assignment_version: int = Field(ge=1)
    candidate_id: str = Field(min_length=1, max_length=96)
    candidate_version: int = Field(ge=1)


class RephraseResponse(TransportModel):
    version: int = Field(ge=1)
    rephrase_id: str = Field(min_length=1, max_length=96)
    original: Candidate
    suggestion: Candidate
    selected_candidate_id: str | None = Field(default=None, min_length=1, max_length=96)
    factual_delta_safe: Literal[True]


class ReviewRequest(TransportModel):
    assignment_version: int = Field(ge=1)
    candidate_id: str = Field(min_length=1, max_length=96)
    candidate_version: int = Field(ge=1)


class ReviewResponse(TransportModel):
    version: int = Field(ge=1)
    review_token: str = Field(min_length=32, max_length=256)
    expires_at: datetime
    question_id: str = Field(min_length=1, max_length=96)
    candidate: Candidate
    attribution: StudentAttribution
    placement: Placement
    preview_context_url: str = Field(min_length=1)


class ConfirmRequest(TransportModel):
    assignment_version: int = Field(ge=1)
    review_token: str = Field(min_length=32, max_length=256)
    candidate_id: str = Field(min_length=1, max_length=96)
    candidate_version: int = Field(ge=1)


class ConfirmResponse(TransportModel):
    version: int = Field(ge=1)
    confirmation_id: str = Field(min_length=1, max_length=96)
    confirmed_answer: ConfirmedAnswer
    replayed: bool


class BeginRevisionRequest(TransportModel):
    assignment_version: int = Field(ge=1)


class BeginRevisionResponse(TransportModel):
    version: int = Field(ge=1)
    question_id: str = Field(min_length=1, max_length=96)
    edit_seed: str
    prior_confirmed_answer: ConfirmedAnswer


class CreateExportRequest(TransportModel):
    assignment_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=16, max_length=128)


class ExportFailure(TransportModel):
    code: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1, max_length=300)
    recoverable: bool


class ExportResponse(TransportModel):
    version: int = Field(ge=1)
    export_id: str = Field(min_length=1, max_length=96)
    assignment_version: int = Field(ge=1)
    status: ExportStatus
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int | None = Field(default=None, ge=1)
    download_url: str | None = Field(default=None, min_length=1)
    failure: ExportFailure | None = None


class RealtimeCredentialRequest(TransportModel):
    assignment_id: str = Field(min_length=1, max_length=96)
    assignment_version: int = Field(ge=1)
    question_id: str = Field(min_length=1, max_length=96)
    mode: RealtimeMode

    @field_validator("mode", mode="before")
    @classmethod
    def parse_realtime_mode(cls, value: object) -> object:
        if type(value) is str:
            return RealtimeMode(value)
        return value


class RealtimeCredentialResponse(TransportModel):
    version: int = Field(ge=1)
    session_id: str = Field(min_length=1, max_length=128)
    client_secret: str = Field(min_length=1)
    expires_at: datetime
    model: str = Field(min_length=1, max_length=128)


class HealthResponse(TransportModel):
    status: Literal["ok"]
