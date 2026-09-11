"""Opaque identifier validation and generation for persisted V2 resources."""

from __future__ import annotations

import re
import secrets

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")


def validate_identifier(value: str, *, label: str = "identifier") -> str:
    """Return a storage-safe opaque identifier or reject it.

    Identifiers are intentionally more restrictive than object names. They can
    be embedded as one path segment without permitting traversal, alternate
    separators, drive prefixes, or dot-segment ambiguity.
    """

    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is malformed")
    return value


def new_identifier(prefix: str) -> str:
    """Create an unguessable public identifier with an explicit resource prefix."""

    validate_identifier(prefix, label="identifier prefix")
    return f"{prefix}_{secrets.token_urlsafe(18)}"
