"""Deterministic UTF-8 assignment manifest persistence with generation CAS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.domain.models import AssignmentManifest, AssignmentStatus
from backend.storage.base import ObjectMetadata, ObjectStore
from backend.storage.errors import ObjectIntegrityError
from backend.storage.keys import assignment_manifest_object_key

MANIFEST_CONTENT_TYPE = "application/json; charset=utf-8"


@dataclass(frozen=True, slots=True)
class VersionedManifest:
    manifest: AssignmentManifest
    generation: int
    sha256: str


class ManifestRepository:
    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    def create(self, manifest: AssignmentManifest) -> VersionedManifest:
        metadata = self._store.create(
            assignment_manifest_object_key(manifest.assignment_id),
            serialize_manifest(manifest),
            content_type=MANIFEST_CONTENT_TYPE,
        )
        return _versioned(manifest, metadata)

    def load(self, assignment_id: str) -> VersionedManifest:
        stored = self._store.read(assignment_manifest_object_key(assignment_id))
        manifest = deserialize_manifest(stored.data)
        if manifest.assignment_id != assignment_id:
            raise ObjectIntegrityError("manifest assignment binding is invalid")
        return _versioned(manifest, stored.metadata)

    def compare_and_swap(
        self,
        observed: VersionedManifest,
        updated: AssignmentManifest,
    ) -> VersionedManifest:
        _validate_manifest_transition(observed.manifest, updated)
        metadata = self._store.compare_and_swap(
            assignment_manifest_object_key(observed.manifest.assignment_id),
            observed.generation,
            serialize_manifest(updated),
            content_type=MANIFEST_CONTENT_TYPE,
        )
        return _versioned(updated, metadata)


def serialize_manifest(manifest: AssignmentManifest) -> bytes:
    """Emit one canonical JSON encoding without ASCII substitution."""

    payload = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return payload.encode("utf-8") + b"\n"


def deserialize_manifest(payload: bytes) -> AssignmentManifest:
    if not isinstance(payload, bytes):
        raise TypeError("manifest payload must be bytes")
    try:
        decoded = payload.decode("utf-8")
        parsed = json.loads(decoded, object_pairs_hook=_reject_duplicate_keys)
        normalized = json.dumps(
            parsed,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return AssignmentManifest.model_validate_json(normalized, strict=True)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ObjectIntegrityError("assignment manifest is invalid") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("assignment manifest contains duplicate keys")
        result[key] = value
    return result


def _versioned(manifest: AssignmentManifest, metadata: ObjectMetadata) -> VersionedManifest:
    return VersionedManifest(manifest, metadata.generation, metadata.sha256)


def _validate_manifest_transition(
    observed: AssignmentManifest, updated: AssignmentManifest
) -> None:
    if updated.assignment_id != observed.assignment_id:
        raise ValueError("manifest assignment_id is immutable")
    if updated.owner_hash != observed.owner_hash:
        raise ValueError("manifest owner binding is immutable")
    if updated.source != observed.source:
        raise ValueError("manifest source reference is immutable")
    if observed.physical_ir is not None and updated.physical_ir != observed.physical_ir:
        raise ValueError("manifest physical IR reference is immutable")
    if (
        observed.physical_ir is None
        and updated.physical_ir is not None
        and not (
            observed.status == AssignmentStatus.ANALYZING
            and updated.status == AssignmentStatus.READY
        )
    ):
        raise ValueError(
            "manifest physical IR reference may only be attached by the ready transition"
        )
    if updated.source_filename != observed.source_filename:
        raise ValueError("manifest source filename is immutable")
    if updated.created_at != observed.created_at or updated.expires_at != observed.expires_at:
        raise ValueError("manifest absolute lifetime is immutable")
    if updated.version < observed.version:
        raise ValueError("manifest public version cannot decrease")
