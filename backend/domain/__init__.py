"""Pure Claros V2 lifecycle models, services, and invariants."""

from backend.domain.errors import (
    AssignmentExpired,
    AssignmentVersionConflict,
    CandidateNotFound,
    DomainError,
    InvalidCandidate,
    InvalidCandidateOrigin,
    NoConfirmedAnswers,
    QuestionNotFound,
    ReviewTokenExpired,
    ReviewTokenInvalid,
    ReviewTokenStale,
)
from backend.domain.models import (
    AssignmentManifest,
    AssignmentStatus,
    Candidate,
    CandidateOrigin,
    ConfirmedAnswer,
    DirectTypedInteraction,
    DirectVoiceInteraction,
    ExportRecord,
    ExportStatus,
    GuidedFinalInteraction,
    ObjectReference,
    Placement,
    PlacementCapability,
    QuestionState,
    RephraseRecord,
    SelectedRephraseInteraction,
    StudentAttribution,
    StudentEditInteraction,
)

_WORKFLOW_EXPORTS = frozenset(
    {
        "ConfirmationResult",
        "ConfirmedAnswerForExport",
        "ExportStartResult",
        "ReviewIssueResult",
        "begin_revision",
        "complete_export",
        "confirm_candidate",
        "confirmed_answers_for_export",
        "fail_export",
        "issue_review",
        "replace_candidate",
        "require_active",
        "require_current_version",
        "start_export",
    }
)


def __getattr__(name: str) -> object:
    """Load workflow operations lazily so security primitives can import models safely."""

    if name in _WORKFLOW_EXPORTS:
        from backend.domain import workflow

        return getattr(workflow, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AssignmentExpired",
    "AssignmentManifest",
    "AssignmentStatus",
    "AssignmentVersionConflict",
    "Candidate",
    "CandidateNotFound",
    "CandidateOrigin",
    "ConfirmationResult",
    "ConfirmedAnswer",
    "ConfirmedAnswerForExport",
    "DirectTypedInteraction",
    "DirectVoiceInteraction",
    "DomainError",
    "ExportRecord",
    "ExportStartResult",
    "ExportStatus",
    "GuidedFinalInteraction",
    "InvalidCandidate",
    "InvalidCandidateOrigin",
    "NoConfirmedAnswers",
    "ObjectReference",
    "Placement",
    "PlacementCapability",
    "QuestionNotFound",
    "QuestionState",
    "RephraseRecord",
    "ReviewIssueResult",
    "ReviewTokenExpired",
    "ReviewTokenInvalid",
    "ReviewTokenStale",
    "SelectedRephraseInteraction",
    "StudentAttribution",
    "StudentEditInteraction",
    "begin_revision",
    "complete_export",
    "confirm_candidate",
    "confirmed_answers_for_export",
    "fail_export",
    "issue_review",
    "replace_candidate",
    "require_active",
    "require_current_version",
    "start_export",
]
