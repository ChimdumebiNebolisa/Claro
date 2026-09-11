"""Persisted, transport-neutral state for the Claros V2 assignment lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.domain.identifiers import validate_identifier

MAX_CANDIDATE_UTF8_BYTES = 8192
MANIFEST_SCHEMA_VERSION = 2


class DomainModel(BaseModel):
    """Strict immutable base model used by pure state transitions."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CandidateOrigin(StrEnum):
    STUDENT_VERBATIM = "student_verbatim"
    STUDENT_NORMALIZED = "student_normalized"
    CLAROS_REPHRASE = "claros_rephrase"
    STUDENT_AFTER_GUIDANCE = "student_after_guidance"
    STUDENT_EDITED = "student_edited"


class StudentAttribution(StrEnum):
    YOUR_WORDS = "Your words"
    SUGGESTED_WORDING = "Suggested wording"


class Placement(StrEnum):
    INLINE = "inline"
    APPENDIX = "appendix"


class PlacementCapability(StrEnum):
    INLINE_POSSIBLE = "inline_possible"
    APPENDIX_ONLY = "appendix_only"


class AssignmentStatus(StrEnum):
    ANALYZING = "analyzing"
    READY = "ready"
    ANALYSIS_FAILED = "analysis_failed"


class ExportStatus(StrEnum):
    CREATING = "creating"
    COMPLETE = "complete"
    FAILED = "failed"


class ObjectReference(DomainModel):
    key: str = Field(min_length=1, max_length=512)
    generation: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    content_type: str = Field(min_length=1, max_length=128)


class Candidate(DomainModel):
    candidate_id: str
    candidate_version: int = Field(ge=1)
    exact_text: str
    origin: CandidateOrigin
    attribution: StudentAttribution
    created_at: datetime

    @model_validator(mode="after")
    def validate_candidate(self) -> Candidate:
        validate_identifier(self.candidate_id, label="candidate_id")
        validate_exact_text(self.exact_text)
        require_aware_datetime(self.created_at, label="created_at")
        expected = attribution_for_origin(self.origin)
        if self.attribution != expected:
            raise ValueError("candidate attribution does not match origin")
        return self


class RephraseRecord(DomainModel):
    rephrase_id: str
    original_candidate_id: str
    original_candidate_version: int = Field(ge=1)
    suggestion_candidate_id: str
    suggestion_candidate_version: int = Field(ge=1)
    suggestion_text: str
    factual_delta_safe: Literal[True]

    @model_validator(mode="after")
    def validate_rephrase(self) -> RephraseRecord:
        validate_identifier(self.rephrase_id, label="rephrase_id")
        validate_identifier(self.original_candidate_id, label="original_candidate_id")
        validate_identifier(self.suggestion_candidate_id, label="suggestion_candidate_id")
        validate_exact_text(self.suggestion_text)
        return self


class ReviewTokenRecord(DomainModel):
    token_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    assignment_id: str
    question_id: str
    candidate_id: str
    candidate_version: int = Field(ge=1)
    exact_text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    placement: Placement
    placement_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    assignment_version: int = Field(ge=1)
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    invalidated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_review(self) -> ReviewTokenRecord:
        validate_identifier(self.assignment_id, label="assignment_id")
        validate_identifier(self.question_id, label="question_id")
        validate_identifier(self.candidate_id, label="candidate_id")
        require_aware_datetime(self.issued_at, label="issued_at")
        require_aware_datetime(self.expires_at, label="expires_at")
        if self.expires_at <= self.issued_at:
            raise ValueError("review expiry must follow issuance")
        if self.consumed_at is not None:
            require_aware_datetime(self.consumed_at, label="consumed_at")
        if self.invalidated_at is not None:
            require_aware_datetime(self.invalidated_at, label="invalidated_at")
        return self


class ConfirmedAnswer(DomainModel):
    confirmation_id: str
    revision: int = Field(ge=1)
    candidate_id: str
    candidate_version: int = Field(ge=1)
    exact_text: str
    exact_text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    origin: CandidateOrigin
    attribution: StudentAttribution
    placement: Placement
    placement_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed_at: datetime

    @model_validator(mode="after")
    def validate_answer(self) -> ConfirmedAnswer:
        validate_identifier(self.confirmation_id, label="confirmation_id")
        validate_identifier(self.candidate_id, label="candidate_id")
        validate_exact_text(self.exact_text)
        require_aware_datetime(self.confirmed_at, label="confirmed_at")
        if self.attribution != attribution_for_origin(self.origin):
            raise ValueError("confirmed attribution does not match origin")
        return self


class ConfirmationReceipt(DomainModel):
    token_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_version: int = Field(ge=1)
    confirmed_answer: ConfirmedAnswer


class RevisionDraft(DomainModel):
    edit_seed: str
    prior_confirmation_id: str
    started_at: datetime

    @model_validator(mode="after")
    def validate_revision(self) -> RevisionDraft:
        validate_exact_text(self.edit_seed)
        validate_identifier(self.prior_confirmation_id, label="prior_confirmation_id")
        require_aware_datetime(self.started_at, label="started_at")
        return self


class QuestionState(DomainModel):
    question_id: str
    index: int = Field(ge=1, le=40)
    display_identifier: str = Field(min_length=1, max_length=64)
    exact_prompt: str = Field(min_length=1)
    prompt_block_ids: tuple[str, ...] = Field(min_length=1)
    context_block_ids: tuple[str, ...] = ()
    instruction: str | None = None
    page_number: int = Field(ge=1, le=8)
    placement_capability: PlacementCapability
    candidate_sequence: int = Field(default=0, ge=0)
    current_candidate: Candidate | None = None
    confirmed_answer: ConfirmedAnswer | None = None
    revision: RevisionDraft | None = None
    rephrases: tuple[RephraseRecord, ...] = ()
    review_tokens: tuple[ReviewTokenRecord, ...] = ()

    @model_validator(mode="after")
    def validate_question(self) -> QuestionState:
        validate_identifier(self.question_id, label="question_id")
        if not self.display_identifier.strip() or any(
            ord(character) < 32 for character in self.display_identifier
        ):
            raise ValueError("question display identifier is invalid")
        if not self.exact_prompt.strip():
            raise ValueError("question prompt cannot be blank")
        if self.instruction is not None and not self.instruction.strip():
            raise ValueError("question instruction cannot be blank")
        evidence_ids = (*self.prompt_block_ids, *self.context_block_ids)
        for block_id in evidence_ids:
            validate_identifier(block_id, label="block_id")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("question evidence block identifiers must be unique")
        if (
            self.current_candidate is not None
            and self.current_candidate.candidate_version > self.candidate_sequence
        ):
            raise ValueError("candidate sequence is behind the current candidate")
        return self


class ExportRecord(DomainModel):
    export_id: str
    assignment_version: int = Field(ge=1)
    idempotency_key_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ExportStatus
    object_ref: ObjectReference | None = None
    manifest_ref: ObjectReference | None = None
    failure_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    created_at: datetime

    @model_validator(mode="after")
    def validate_export(self) -> ExportRecord:
        validate_identifier(self.export_id, label="export_id")
        require_aware_datetime(self.created_at, label="created_at")
        if self.status == ExportStatus.COMPLETE and self.object_ref is None:
            raise ValueError("complete export requires an object reference")
        if self.status == ExportStatus.FAILED and self.failure_code is None:
            raise ValueError("failed export requires a failure code")
        return self


class AssignmentManifest(DomainModel):
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    assignment_id: str
    owner_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: int = Field(ge=1)
    status: AssignmentStatus
    title: str = Field(min_length=1, max_length=255)
    source_filename: str = Field(min_length=1, max_length=255)
    source: ObjectReference
    physical_ir: ObjectReference | None = None
    questions: tuple[QuestionState, ...] = ()
    exports: tuple[ExportRecord, ...] = ()
    confirmation_receipts: tuple[ConfirmationReceipt, ...] = ()
    warnings: tuple[str, ...] = ()
    failure_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_manifest(self) -> AssignmentManifest:
        validate_identifier(self.assignment_id, label="assignment_id")
        if (
            not self.source_filename.strip()
            or self.source_filename in {".", ".."}
            or "/" in self.source_filename
            or "\\" in self.source_filename
            or any(ord(character) < 32 for character in self.source_filename)
        ):
            raise ValueError("source filename is invalid")
        require_aware_datetime(self.created_at, label="created_at")
        require_aware_datetime(self.expires_at, label="expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("assignment expiry must follow creation")
        ordered = tuple(sorted(self.questions, key=lambda item: item.index))
        if self.questions != ordered:
            raise ValueError("questions must remain in source order")
        question_ids = [question.question_id for question in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("question identifiers must be unique")
        if len(self.questions) > 40:
            raise ValueError("assignment exceeds the supported question limit")
        export_ids = [item.export_id for item in self.exports]
        if len(export_ids) != len(set(export_ids)):
            raise ValueError("export identifiers must be unique")
        receipt_ids = [item.token_digest for item in self.confirmation_receipts]
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError("confirmation receipts must be unique per review token")
        return self


class DirectTypedInteraction(DomainModel):
    kind: Literal["direct_typed"] = "direct_typed"


class DirectVoiceInteraction(DomainModel):
    kind: Literal["direct_voice"] = "direct_voice"
    realtime_session_id: str
    source_turn_ids: tuple[str, ...] = Field(min_length=1, max_length=24)
    normalization: Literal["none", "punctuation_only"]


class GuidedFinalInteraction(DomainModel):
    kind: Literal["guided_final"] = "guided_final"
    realtime_session_id: str
    source_turn_ids: tuple[str, ...] = Field(min_length=1, max_length=24)
    input: Literal["typed", "voice"]


class StudentEditInteraction(DomainModel):
    kind: Literal["student_edit"] = "student_edit"
    prior_candidate_id: str
    prior_candidate_version: int = Field(ge=1)


class SelectedRephraseInteraction(DomainModel):
    kind: Literal["selected_rephrase"] = "selected_rephrase"
    rephrase_id: str
    suggestion_candidate_id: str


CandidateInteraction = Annotated[
    DirectTypedInteraction
    | DirectVoiceInteraction
    | GuidedFinalInteraction
    | StudentEditInteraction
    | SelectedRephraseInteraction,
    Field(discriminator="kind"),
]


def attribution_for_origin(origin: CandidateOrigin) -> StudentAttribution:
    if origin == CandidateOrigin.CLAROS_REPHRASE:
        return StudentAttribution.SUGGESTED_WORDING
    return StudentAttribution.YOUR_WORDS


def validate_exact_text(value: str) -> str:
    """Validate the resource envelope without changing a single code point."""

    if not isinstance(value, str):
        raise ValueError("candidate text must be a string")
    if "\x00" in value:
        raise ValueError("candidate text cannot contain a NUL character")
    if not value.strip():
        raise ValueError("candidate text cannot be blank")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("candidate text must be valid UTF-8") from exc
    if len(encoded) > MAX_CANDIDATE_UTF8_BYTES:
        raise ValueError(f"candidate text exceeds {MAX_CANDIDATE_UTF8_BYTES} UTF-8 bytes")
    return value


def require_aware_datetime(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value.astimezone(UTC)
