"""Transport-neutral failures raised by pure Claros domain operations."""

from __future__ import annotations


class DomainError(RuntimeError):
    """A bounded, machine-readable domain failure."""

    code = "domain_error"
    recoverable = True


class AssignmentVersionConflict(DomainError):
    code = "assignment_version_conflict"

    def __init__(self, current_version: int) -> None:
        super().__init__("The assignment changed. Reload it and try again.")
        self.current_version = current_version


class AssignmentExpired(DomainError):
    code = "assignment_expired"


class QuestionNotFound(DomainError):
    code = "question_not_found"


class CandidateNotFound(DomainError):
    code = "candidate_not_found"


class InvalidCandidate(DomainError):
    code = "invalid_candidate"


class InvalidCandidateOrigin(DomainError):
    code = "invalid_candidate_origin"


class ReviewTokenInvalid(DomainError):
    code = "invalid_review"


class ReviewTokenExpired(DomainError):
    code = "review_expired"


class ReviewTokenStale(DomainError):
    code = "stale_review"


class NoConfirmedAnswers(DomainError):
    code = "no_confirmed_answers"
