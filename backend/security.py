"""Signed anonymous ownership and opaque review-token primitives."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from itsdangerous import BadData, URLSafeSerializer

from backend.config import canonical_origin
from backend.domain.identifiers import validate_identifier
from backend.domain.models import Placement, ReviewTokenRecord

OWNER_SESSION_TTL_SECONDS = 24 * 60 * 60
REVIEW_TOKEN_TTL_SECONDS = 10 * 60
_OWNER_COOKIE_SALT = "claros-v2-owner-session"
_OWNER_HASH_CONTEXT = b"claros/v2/owner-hash\0"
_REVIEW_TOKEN_CONTEXT = b"claros/v2/review-token\0"
_CONFIRM_REQUEST_CONTEXT = b"claros/v2/confirmation-request\0"
_INVALID_REVIEW_TOKEN_BYTES = b"\0"


class OwnerSessionError(ValueError):
    """The signed owner cookie is invalid or outside its absolute lifetime."""


class OwnerSessionExpired(OwnerSessionError):
    """The signed owner cookie reached its absolute expiry."""


class AssignmentAccessDenied(LookupError):
    """A deliberately non-disclosing assignment authorization failure."""

    code = "assignment_not_found"

    def __init__(self) -> None:
        super().__init__("The assignment could not be found.")


class OriginDenied(PermissionError):
    code = "origin_not_allowed"


@dataclass(frozen=True, slots=True)
class OwnerSession:
    owner_id: str
    issued_at: datetime
    expires_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _current_time(now: datetime | None) -> datetime:
    if now is None:
        return _utc_now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("security timestamps must include a timezone")
    return now.astimezone(UTC)


def _secret_bytes(secret: str | bytes) -> bytes:
    if isinstance(secret, bytes):
        if not secret:
            raise ValueError("signing secret cannot be empty")
        return secret
    if not isinstance(secret, str) or not secret:
        raise ValueError("signing secret cannot be empty")
    return secret.encode("utf-8")


def _timestamp(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("security timestamps must include a timezone")
    return int(value.astimezone(UTC).timestamp())


def _from_timestamp(value: Any, *, label: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OwnerSessionError(f"owner session {label} is invalid")
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise OwnerSessionError(f"owner session {label} is invalid") from exc


def create_owner_session(
    secret: str | bytes,
    *,
    now: datetime | None = None,
    ttl_seconds: int = OWNER_SESSION_TTL_SECONDS,
    owner_id_factory: Callable[[], str] | None = None,
) -> tuple[OwnerSession, str]:
    """Issue a signed cookie carrying only an opaque owner identifier and bounds."""

    if isinstance(ttl_seconds, bool) or not 0 < ttl_seconds <= OWNER_SESSION_TTL_SECONDS:
        raise ValueError("owner session TTL must be between 1 second and 24 hours")
    issued_at = _current_time(now)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    owner_id = (
        owner_id_factory() if owner_id_factory is not None else f"own_{secrets.token_urlsafe(24)}"
    )
    validate_identifier(owner_id, label="owner_id")
    payload = {
        "expires_at": _timestamp(expires_at),
        "issued_at": _timestamp(issued_at),
        "owner_id": owner_id,
        "version": 1,
    }
    serializer = URLSafeSerializer(_secret_bytes(secret), salt=_OWNER_COOKIE_SALT)
    cookie = serializer.dumps(payload)
    return OwnerSession(owner_id, issued_at, expires_at), cookie


def verify_owner_session(
    cookie: str,
    secret: str | bytes,
    *,
    now: datetime | None = None,
    max_ttl_seconds: int = OWNER_SESSION_TTL_SECONDS,
) -> OwnerSession:
    """Verify signature, shape, clock bounds, and absolute session expiry."""

    if not isinstance(cookie, str) or not cookie or len(cookie) > 2048:
        raise OwnerSessionError("owner session is invalid")
    try:
        payload = URLSafeSerializer(_secret_bytes(secret), salt=_OWNER_COOKIE_SALT).loads(cookie)
    except BadData as exc:
        raise OwnerSessionError("owner session is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "expires_at",
        "issued_at",
        "owner_id",
        "version",
    }:
        raise OwnerSessionError("owner session is invalid")
    if payload["version"] != 1:
        raise OwnerSessionError("owner session version is invalid")
    try:
        owner_id = validate_identifier(payload["owner_id"], label="owner_id")
    except (TypeError, ValueError) as exc:
        raise OwnerSessionError("owner session is invalid") from exc
    issued_at = _from_timestamp(payload["issued_at"], label="issued_at")
    expires_at = _from_timestamp(payload["expires_at"], label="expires_at")
    current = _current_time(now)
    if issued_at > current + timedelta(seconds=60):
        raise OwnerSessionError("owner session issuance is invalid")
    lifetime = int((expires_at - issued_at).total_seconds())
    if lifetime <= 0 or lifetime > max_ttl_seconds:
        raise OwnerSessionError("owner session lifetime is invalid")
    if current >= expires_at:
        raise OwnerSessionExpired("owner session has expired")
    return OwnerSession(owner_id, issued_at, expires_at)


def owner_hash(owner_id: str, secret: str | bytes) -> str:
    """Return the non-reversible manifest binding for an opaque owner ID."""

    validate_identifier(owner_id, label="owner_id")
    return hmac.new(
        _secret_bytes(secret),
        _OWNER_HASH_CONTEXT + owner_id.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def require_assignment_owner(
    *,
    cookie: str | None,
    stored_owner_hash: str,
    secret: str | bytes,
    assignment_expires_at: datetime,
    now: datetime | None = None,
) -> OwnerSession:
    """Authorize without distinguishing missing, invalid, expired, or cross-owner data."""

    current = _current_time(now)
    try:
        if assignment_expires_at.tzinfo is None or assignment_expires_at.utcoffset() is None:
            raise OwnerSessionError("assignment expiry is invalid")
        if current >= assignment_expires_at.astimezone(UTC):
            raise OwnerSessionExpired("assignment has expired")
        session = verify_owner_session(cookie or "", secret, now=current)
        actual_hash = owner_hash(session.owner_id, secret)
        if not hmac.compare_digest(actual_hash, stored_owner_hash):
            raise OwnerSessionError("owner binding does not match")
    except (OwnerSessionError, TypeError, ValueError) as exc:
        raise AssignmentAccessDenied from exc
    return session


def require_same_origin(origin: str | None, public_origin: str) -> None:
    """Reject cookie-authenticated mutations not sent from the configured origin."""

    try:
        matches = origin is not None and canonical_origin(origin) == canonical_origin(public_origin)
    except ValueError as exc:
        raise OriginDenied("The request origin is not allowed.") from exc
    if not matches:
        raise OriginDenied("The request origin is not allowed.")


def exact_text_hash(text: str) -> str:
    try:
        payload = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("text must be valid UTF-8") from exc
    return hashlib.sha256(payload).hexdigest()


def review_token_digest(token: str, secret: str | bytes) -> str:
    valid = isinstance(token, str) and token.startswith("rvw_") and len(token) <= 256
    # Digest a fixed sentinel for malformed values so callers retain uniform lookup behavior.
    payload = token.encode("utf-8") if valid else _INVALID_REVIEW_TOKEN_BYTES
    return hmac.new(
        _secret_bytes(secret),
        _REVIEW_TOKEN_CONTEXT + payload,
        hashlib.sha256,
    ).hexdigest()


def issue_review_token(
    *,
    secret: str | bytes,
    owner_hash_value: str,
    assignment_id: str,
    question_id: str,
    candidate_id: str,
    candidate_version: int,
    text: str,
    placement: Placement,
    placement_hash: str,
    assignment_version: int,
    now: datetime | None = None,
    ttl_seconds: int = REVIEW_TOKEN_TTL_SECONDS,
    token_factory: Callable[[], str] | None = None,
) -> tuple[str, ReviewTokenRecord]:
    """Return a random bearer value and its digest-only durable binding."""

    if isinstance(ttl_seconds, bool) or not 0 < ttl_seconds <= REVIEW_TOKEN_TTL_SECONDS:
        raise ValueError("review token TTL must be between 1 and 600 seconds")
    issued_at = _current_time(now)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    token = token_factory() if token_factory is not None else f"rvw_{secrets.token_urlsafe(32)}"
    if not token.startswith("rvw_") or not 32 <= len(token) <= 256:
        raise ValueError("review token factory returned an invalid token")
    record = ReviewTokenRecord(
        token_digest=review_token_digest(token, secret),
        owner_hash=owner_hash_value,
        assignment_id=assignment_id,
        question_id=question_id,
        candidate_id=candidate_id,
        candidate_version=candidate_version,
        exact_text_hash=exact_text_hash(text),
        placement=placement,
        placement_hash=placement_hash,
        assignment_version=assignment_version,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return token, record


def confirmation_request_digest(
    *,
    token_digest: str,
    assignment_id: str,
    question_id: str,
    candidate_id: str,
    candidate_version: int,
    assignment_version: int,
) -> str:
    """Hash the exact confirmation request for durable replay comparison."""

    payload = json.dumps(
        {
            "assignment_id": assignment_id,
            "assignment_version": assignment_version,
            "candidate_id": candidate_id,
            "candidate_version": candidate_version,
            "question_id": question_id,
            "token_digest": token_digest,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(_CONFIRM_REQUEST_CONTEXT + payload).hexdigest()
