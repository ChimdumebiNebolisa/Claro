"""Closed object-key construction for private Claros assignment artifacts."""

from __future__ import annotations

import re

from backend.domain.identifiers import validate_identifier
from backend.storage.errors import InvalidObjectKey

_OBJECT_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_object_key(key: str) -> str:
    if not isinstance(key, str) or not key or len(key) > 512:
        raise InvalidObjectKey("object key is malformed")
    if "\\" in key or key.startswith("/") or key.endswith("/"):
        raise InvalidObjectKey("object key is malformed")
    segments = key.split("/")
    if any(
        segment in {"", ".", ".."}
        or _OBJECT_SEGMENT.fullmatch(segment) is None
        or segment.startswith(".")
        for segment in segments
    ):
        raise InvalidObjectKey("object key is malformed")
    return key


def assignment_prefix(assignment_id: str) -> str:
    return f"assignments/{validate_identifier(assignment_id, label='assignment_id')}"


def source_object_key(assignment_id: str) -> str:
    return f"{assignment_prefix(assignment_id)}/source/original.pdf"


def physical_ir_object_key(assignment_id: str) -> str:
    return f"{assignment_prefix(assignment_id)}/analysis/physical-ir.json"


def assignment_manifest_object_key(assignment_id: str) -> str:
    return f"{assignment_prefix(assignment_id)}/manifest/assignment.json"


def preview_object_key(assignment_id: str, page_number: int) -> str:
    if isinstance(page_number, bool) or not 1 <= page_number <= 8:
        raise ValueError("page_number must be between 1 and 8")
    return f"{assignment_prefix(assignment_id)}/previews/page-{page_number}.png"


def export_prefix(assignment_id: str, export_id: str) -> str:
    safe_export_id = validate_identifier(export_id, label="export_id")
    return f"{assignment_prefix(assignment_id)}/exports/{safe_export_id}"


def export_pdf_object_key(assignment_id: str, export_id: str) -> str:
    return f"{export_prefix(assignment_id, export_id)}/completed.pdf"


def export_manifest_object_key(assignment_id: str, export_id: str) -> str:
    return f"{export_prefix(assignment_id, export_id)}/manifest.json"
