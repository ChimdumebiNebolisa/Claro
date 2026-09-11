"""Pure versioned operations for candidates, review, confirmation, and export."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.domain.errors import (
    AssignmentExpired,
    AssignmentVersionConflict,
    CandidateNotFound,
    InvalidCandidate,
    InvalidCandidateOrigin,
    NoConfirmedAnswers,
    QuestionNotFound,
    ReviewTokenExpired,
    ReviewTokenInvalid,
    ReviewTokenStale,
)
from backend.domain.identifiers import new_identifier, validate_identifier
from backend.domain.models import (
    AssignmentManifest,
    AssignmentStatus,
    Candidate,
    CandidateInteraction,
    CandidateOrigin,
    ConfirmationReceipt,
    ConfirmedAnswer,
    DirectTypedInteraction,
    DirectVoiceInteraction,
    ExportRecord,
    ExportStatus,
    GuidedFinalInteraction,
    ObjectReference,
    Placement,
    QuestionState,
    ReviewTokenRecord,
    RevisionDraft,
    SelectedRephraseInteraction,
    StudentEditInteraction,
    attribution_for_origin,
    require_aware_datetime,
    validate_exact_text,
)
from backend.security import (
    confirmation_request_digest,
    exact_text_hash,
    issue_review_token,
    review_token_digest,
)


@dataclass(frozen=True, slots=True)
class ReviewIssueResult:
    manifest: AssignmentManifest
    review_token: str
    record: ReviewTokenRecord


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    manifest: AssignmentManifest
    version: int
    confirmed_answer: ConfirmedAnswer
    replayed: bool


@dataclass(frozen=True, slots=True)
class ExportStartResult:
    manifest: AssignmentManifest
    export: ExportRecord
    replayed: bool


@dataclass(frozen=True, slots=True)
class ConfirmedAnswerForExport:
    question_id: str
    question_index: int
    display_identifier: str
    exact_prompt: str
    prompt_block_ids: tuple[str, ...]
    context_block_ids: tuple[str, ...]
    page_number: int
    answer: ConfirmedAnswer


def utc_now() -> datetime:
    return datetime.now(UTC)


def _current_time(now: datetime | None) -> datetime:
    return utc_now() if now is None else require_aware_datetime(now, label="now")


def require_current_version(manifest: AssignmentManifest, supplied_version: int) -> None:
    if supplied_version != manifest.version:
        raise AssignmentVersionConflict(manifest.version)


def require_active(manifest: AssignmentManifest, *, now: datetime | None = None) -> None:
    current = _current_time(now)
    if current >= manifest.expires_at.astimezone(UTC):
        raise AssignmentExpired("This assignment has expired.")


def replace_candidate(
    manifest: AssignmentManifest,
    *,
    question_id: str,
    assignment_version: int,
    exact_text: str,
    origin: CandidateOrigin,
    interaction: CandidateInteraction,
    now: datetime | None = None,
    candidate_id_factory: Callable[[], str] | None = None,
) -> tuple[AssignmentManifest, Candidate]:
    """Replace one candidate exactly once and invalidate prior review authority."""

    require_active(manifest, now=now)
    require_current_version(manifest, assignment_version)
    if manifest.status != AssignmentStatus.READY:
        raise InvalidCandidate("The worksheet is not ready for an answer.")
    validate_exact_text(exact_text)
    index, question = _find_question(manifest, question_id)
    _validate_origin(question, exact_text=exact_text, origin=origin, interaction=interaction)
    created_at = _current_time(now)
    candidate_sequence = question.candidate_sequence + 1
    candidate_id = (
        candidate_id_factory() if candidate_id_factory is not None else new_identifier("cand")
    )
    validate_identifier(candidate_id, label="candidate_id")
    candidate = Candidate(
        candidate_id=candidate_id,
        candidate_version=candidate_sequence,
        exact_text=exact_text,
        origin=origin,
        attribution=attribution_for_origin(origin),
        created_at=created_at,
    )
    updated_question = question.model_copy(
        update={
            "candidate_sequence": candidate_sequence,
            "current_candidate": candidate,
            "revision": question.revision,
            "review_tokens": _invalidate_reviews(question.review_tokens, created_at),
        }
    )
    updated = _replace_question(manifest, index, updated_question).model_copy(
        update={"version": manifest.version + 1}
    )
    return updated, candidate


def issue_review(
    manifest: AssignmentManifest,
    *,
    owner_hash: str,
    question_id: str,
    candidate_id: str,
    candidate_version: int,
    assignment_version: int,
    placement: Placement,
    placement_hash: str,
    token_secret: str | bytes,
    now: datetime | None = None,
    ttl_seconds: int = 600,
    token_factory: Callable[[], str] | None = None,
) -> ReviewIssueResult:
    """Persist a digest-only, exact-text and placement-bound review record."""

    require_active(manifest, now=now)
    require_current_version(manifest, assignment_version)
    index, question = _find_question(manifest, question_id)
    candidate = _require_candidate(question, candidate_id, candidate_version)
    if not hmac.compare_digest(manifest.owner_hash, owner_hash):
        raise ReviewTokenStale("The review no longer matches this assignment.")
    token, record = issue_review_token(
        secret=token_secret,
        owner_hash_value=owner_hash,
        assignment_id=manifest.assignment_id,
        question_id=question.question_id,
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        text=candidate.exact_text,
        placement=placement,
        placement_hash=placement_hash,
        assignment_version=manifest.version,
        now=now,
        ttl_seconds=ttl_seconds,
        token_factory=token_factory,
    )
    updated_question = question.model_copy(
        update={"review_tokens": (*question.review_tokens, record)}
    )
    # Review issuance changes durable manifest generation, not public assignment version.
    updated = _replace_question(manifest, index, updated_question)
    return ReviewIssueResult(updated, token, record)


def confirm_candidate(
    manifest: AssignmentManifest,
    *,
    owner_hash: str,
    question_id: str,
    review_token: str,
    candidate_id: str,
    candidate_version: int,
    assignment_version: int,
    token_secret: str | bytes,
    now: datetime | None = None,
    confirmation_id_factory: Callable[[], str] | None = None,
) -> ConfirmationResult:
    """Confirm once, while returning the durable result for an exact network replay."""

    require_active(manifest, now=now)
    current = _current_time(now)
    token_digest = review_token_digest(review_token, token_secret)
    index, question = _find_question(manifest, question_id)
    record = _find_review_record(question, token_digest)
    if record is None:
        raise ReviewTokenInvalid("The review token is invalid.")
    if current >= record.expires_at.astimezone(UTC):
        raise ReviewTokenExpired("The review has expired. Review the answer again.")
    if record.invalidated_at is not None:
        raise ReviewTokenStale("The answer changed after this review.")
    if not hmac.compare_digest(record.owner_hash, owner_hash):
        raise ReviewTokenStale("The review no longer matches this assignment.")

    request_digest = confirmation_request_digest(
        token_digest=token_digest,
        assignment_id=manifest.assignment_id,
        question_id=question_id,
        candidate_id=candidate_id,
        candidate_version=candidate_version,
        assignment_version=assignment_version,
    )
    receipt = _find_receipt(manifest, token_digest)
    if receipt is not None:
        if not hmac.compare_digest(receipt.request_digest, request_digest):
            raise ReviewTokenStale("The confirmation request differs from its review.")
        return ConfirmationResult(
            manifest=manifest,
            version=receipt.result_version,
            confirmed_answer=receipt.confirmed_answer,
            replayed=True,
        )
    if record.consumed_at is not None:
        raise ReviewTokenInvalid("The review has already been used.")

    require_current_version(manifest, assignment_version)
    candidate = _require_candidate(question, candidate_id, candidate_version)
    if (
        record.assignment_id != manifest.assignment_id
        or record.question_id != question.question_id
        or record.candidate_id != candidate.candidate_id
        or record.candidate_version != candidate.candidate_version
        or record.assignment_version != manifest.version
        or not hmac.compare_digest(record.exact_text_hash, exact_text_hash(candidate.exact_text))
    ):
        raise ReviewTokenStale("The answer changed after this review.")

    confirmation_id = (
        confirmation_id_factory() if confirmation_id_factory is not None else new_identifier("cnf")
    )
    validate_identifier(confirmation_id, label="confirmation_id")
    revision = (question.confirmed_answer.revision + 1) if question.confirmed_answer else 1
    confirmed_answer = ConfirmedAnswer(
        confirmation_id=confirmation_id,
        revision=revision,
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        exact_text=candidate.exact_text,
        exact_text_hash=record.exact_text_hash,
        origin=candidate.origin,
        attribution=candidate.attribution,
        placement=record.placement,
        placement_hash=record.placement_hash,
        confirmed_at=current,
    )
    consumed_record = record.model_copy(update={"consumed_at": current})
    updated_tokens = tuple(
        consumed_record if item.token_digest == token_digest else item
        for item in question.review_tokens
    )
    updated_question = question.model_copy(
        update={
            "confirmed_answer": confirmed_answer,
            "revision": None,
            "review_tokens": updated_tokens,
        }
    )
    result_version = manifest.version + 1
    receipt = ConfirmationReceipt(
        token_digest=token_digest,
        request_digest=request_digest,
        result_version=result_version,
        confirmed_answer=confirmed_answer,
    )
    updated = _replace_question(manifest, index, updated_question).model_copy(
        update={
            "version": result_version,
            "confirmation_receipts": (*manifest.confirmation_receipts, receipt),
        }
    )
    return ConfirmationResult(updated, result_version, confirmed_answer, False)


def begin_revision(
    manifest: AssignmentManifest,
    *,
    question_id: str,
    assignment_version: int,
    now: datetime | None = None,
) -> tuple[AssignmentManifest, RevisionDraft]:
    """Open a neutral edit seed while retaining the last confirmed export truth."""

    require_active(manifest, now=now)
    require_current_version(manifest, assignment_version)
    index, question = _find_question(manifest, question_id)
    if question.confirmed_answer is None:
        raise CandidateNotFound("There is no confirmed answer to revise.")
    started_at = _current_time(now)
    revision = RevisionDraft(
        edit_seed=question.confirmed_answer.exact_text,
        prior_confirmation_id=question.confirmed_answer.confirmation_id,
        started_at=started_at,
    )
    updated_question = question.model_copy(
        update={
            "current_candidate": None,
            "revision": revision,
            "review_tokens": _invalidate_reviews(question.review_tokens, started_at),
        }
    )
    updated = _replace_question(manifest, index, updated_question).model_copy(
        update={"version": manifest.version + 1}
    )
    return updated, revision


def start_export(
    manifest: AssignmentManifest,
    *,
    assignment_version: int,
    idempotency_key: str,
    now: datetime | None = None,
    stale_after_seconds: int = 300,
) -> ExportStartResult:
    """Create one stable export identity per public assignment version."""

    require_active(manifest, now=now)
    require_current_version(manifest, assignment_version)
    if not confirmed_answers_for_export(manifest):
        raise NoConfirmedAnswers("Confirm at least one answer before exporting.")
    current = _current_time(now)
    if (
        isinstance(stale_after_seconds, bool)
        or stale_after_seconds < 1
        or stale_after_seconds > 300
    ):
        raise ValueError("export stale threshold must be between 1 and 300 seconds")
    idempotency_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    for index, existing in enumerate(manifest.exports):
        if existing.assignment_version != manifest.version:
            continue
        if existing.status == ExportStatus.COMPLETE:
            return ExportStartResult(manifest, existing, True)
        if existing.status == ExportStatus.CREATING:
            age_seconds = (current - existing.created_at.astimezone(UTC)).total_seconds()
            if age_seconds < stale_after_seconds:
                return ExportStartResult(manifest, existing, True)
        retried = existing.model_copy(
            update={
                "status": ExportStatus.CREATING,
                "failure_code": None,
                "idempotency_key_hash": idempotency_hash,
                "created_at": current,
            }
        )
        exports = list(manifest.exports)
        exports[index] = retried
        return ExportStartResult(
            manifest.model_copy(update={"exports": tuple(exports)}), retried, True
        )

    digest = hashlib.sha256(
        f"{manifest.assignment_id}\0{manifest.version}".encode("ascii")
    ).hexdigest()[:20]
    export = ExportRecord(
        export_id=f"exp_{manifest.version}_{digest}",
        assignment_version=manifest.version,
        idempotency_key_hash=idempotency_hash,
        status=ExportStatus.CREATING,
        created_at=current,
    )
    updated = manifest.model_copy(update={"exports": (*manifest.exports, export)})
    # Export lifecycle changes persisted generation but not the public assignment version.
    return ExportStartResult(updated, export, False)


def complete_export(
    manifest: AssignmentManifest,
    *,
    export_id: str,
    object_ref: ObjectReference,
    manifest_ref: ObjectReference,
) -> tuple[AssignmentManifest, ExportRecord]:
    return _update_export(
        manifest,
        export_id=export_id,
        updates={
            "status": ExportStatus.COMPLETE,
            "object_ref": object_ref,
            "manifest_ref": manifest_ref,
            "failure_code": None,
        },
    )


def fail_export(
    manifest: AssignmentManifest, *, export_id: str, failure_code: str
) -> tuple[AssignmentManifest, ExportRecord]:
    if not failure_code or not failure_code.replace("_", "").isalnum():
        raise ValueError("failure code must be machine-readable")
    return _update_export(
        manifest,
        export_id=export_id,
        updates={"status": ExportStatus.FAILED, "failure_code": failure_code},
    )


def confirmed_answers_for_export(
    manifest: AssignmentManifest,
) -> tuple[ConfirmedAnswerForExport, ...]:
    """Project only latest confirmed revisions in immutable source order."""

    return tuple(
        ConfirmedAnswerForExport(
            question_id=question.question_id,
            question_index=question.index,
            display_identifier=question.display_identifier,
            exact_prompt=question.exact_prompt,
            prompt_block_ids=question.prompt_block_ids,
            context_block_ids=question.context_block_ids,
            page_number=question.page_number,
            answer=question.confirmed_answer,
        )
        for question in manifest.questions
        if question.confirmed_answer is not None
    )


def _validate_origin(
    question: QuestionState,
    *,
    exact_text: str,
    origin: CandidateOrigin,
    interaction: CandidateInteraction,
) -> None:
    expected: CandidateOrigin
    if isinstance(interaction, DirectTypedInteraction):
        expected = CandidateOrigin.STUDENT_VERBATIM
    elif isinstance(interaction, DirectVoiceInteraction):
        expected = (
            CandidateOrigin.STUDENT_NORMALIZED
            if interaction.normalization == "punctuation_only"
            else CandidateOrigin.STUDENT_VERBATIM
        )
    elif isinstance(interaction, GuidedFinalInteraction):
        expected = CandidateOrigin.STUDENT_AFTER_GUIDANCE
    elif isinstance(interaction, StudentEditInteraction):
        expected = CandidateOrigin.STUDENT_EDITED
        prior = question.current_candidate
        prior_id = prior.candidate_id if prior else None
        prior_version = prior.candidate_version if prior else None
        if prior is None and question.confirmed_answer is not None:
            prior_id = question.confirmed_answer.candidate_id
            prior_version = question.confirmed_answer.candidate_version
        if (
            interaction.prior_candidate_id != prior_id
            or interaction.prior_candidate_version != prior_version
        ):
            raise InvalidCandidateOrigin("The edit does not match the current answer.")
    elif isinstance(interaction, SelectedRephraseInteraction):
        expected = CandidateOrigin.CLAROS_REPHRASE
        matching = next(
            (
                item
                for item in question.rephrases
                if item.rephrase_id == interaction.rephrase_id
                and item.suggestion_candidate_id == interaction.suggestion_candidate_id
            ),
            None,
        )
        if matching is None or matching.suggestion_text != exact_text:
            raise InvalidCandidateOrigin("The suggestion is not a valid server rephrase.")
    else:  # pragma: no cover - exhaustive defensive boundary
        raise InvalidCandidateOrigin("The interaction path is unsupported.")
    if origin != expected:
        raise InvalidCandidateOrigin("The candidate origin does not match its interaction.")


def _find_question(manifest: AssignmentManifest, question_id: str) -> tuple[int, QuestionState]:
    for index, question in enumerate(manifest.questions):
        if question.question_id == question_id:
            return index, question
    raise QuestionNotFound("The question could not be found.")


def _replace_question(
    manifest: AssignmentManifest, index: int, question: QuestionState
) -> AssignmentManifest:
    questions = list(manifest.questions)
    questions[index] = question
    return manifest.model_copy(update={"questions": tuple(questions)})


def _require_candidate(
    question: QuestionState, candidate_id: str, candidate_version: int
) -> Candidate:
    candidate = question.current_candidate
    if (
        candidate is None
        or candidate.candidate_id != candidate_id
        or candidate.candidate_version != candidate_version
    ):
        raise CandidateNotFound("The answer candidate is no longer current.")
    return candidate


def _invalidate_reviews(
    records: tuple[ReviewTokenRecord, ...], invalidated_at: datetime
) -> tuple[ReviewTokenRecord, ...]:
    return tuple(
        item
        if item.invalidated_at is not None
        else item.model_copy(update={"invalidated_at": invalidated_at})
        for item in records
    )


def _find_review_record(question: QuestionState, token_digest: str) -> ReviewTokenRecord | None:
    for record in question.review_tokens:
        if hmac.compare_digest(record.token_digest, token_digest):
            return record
    return None


def _find_receipt(manifest: AssignmentManifest, token_digest: str) -> ConfirmationReceipt | None:
    for receipt in manifest.confirmation_receipts:
        if hmac.compare_digest(receipt.token_digest, token_digest):
            return receipt
    return None


def _update_export(
    manifest: AssignmentManifest, *, export_id: str, updates: dict[str, object]
) -> tuple[AssignmentManifest, ExportRecord]:
    validate_identifier(export_id, label="export_id")
    exports = list(manifest.exports)
    for index, existing in enumerate(exports):
        if existing.export_id == export_id:
            updated = existing.model_copy(update=updates)
            exports[index] = updated
            return manifest.model_copy(update={"exports": tuple(exports)}), updated
    raise LookupError("The export could not be found.")
