from __future__ import annotations

from pathlib import Path

import pytest

from backend.domain.models import AssignmentStatus, ObjectReference
from backend.storage import (
    GenerationConflict,
    LocalObjectStore,
    ManifestRepository,
    ObjectIntegrityError,
    deserialize_manifest,
    serialize_manifest,
)
from backend.tests.domain.factories import make_manifest


def test_manifest_serialization_is_deterministic_utf8_without_ascii_substitution() -> None:
    manifest = make_manifest()

    first = serialize_manifest(manifest)
    second = serialize_manifest(manifest.model_copy(deep=True))

    assert first == second
    assert "Biology — cells & energy".encode() in first
    assert b"\\u2014" not in first
    assert deserialize_manifest(first) == manifest


def test_manifest_deserialization_rejects_duplicate_keys_and_invalid_utf8() -> None:
    with pytest.raises(ObjectIntegrityError):
        deserialize_manifest(b'{"schema_version":2,"schema_version":2}')
    with pytest.raises(ObjectIntegrityError):
        deserialize_manifest(b"\xff")


def test_repository_uses_cas_and_never_changes_source_binding(
    tmp_path: Path,
) -> None:
    repository = ManifestRepository(LocalObjectStore(tmp_path / "objects"))
    initial = repository.create(make_manifest())
    updated_manifest = initial.manifest.model_copy(update={"version": 2})

    updated = repository.compare_and_swap(initial, updated_manifest)

    assert updated.generation == initial.generation + 1
    assert repository.load(initial.manifest.assignment_id).manifest.version == 2
    with pytest.raises(GenerationConflict):
        repository.compare_and_swap(initial, updated_manifest)

    changed_source = updated.manifest.source.model_copy(update={"generation": 8})
    with pytest.raises(ValueError, match="source reference is immutable"):
        repository.compare_and_swap(
            updated,
            updated.manifest.model_copy(update={"source": changed_source}),
        )
    with pytest.raises(ValueError, match="source filename is immutable"):
        repository.compare_and_swap(
            updated,
            updated.manifest.model_copy(update={"source_filename": "renamed.pdf"}),
        )


def test_physical_ir_can_be_attached_once_only_by_ready_transition(tmp_path: Path) -> None:
    repository = ManifestRepository(LocalObjectStore(tmp_path / "objects"))
    analyzing_manifest = make_manifest(
        question_count=0,
        status=AssignmentStatus.ANALYZING,
    )
    analyzing = repository.create(analyzing_manifest)
    physical_ir = ObjectReference(
        key="assignments/asg_test_01/analysis/physical-ir.json",
        generation=1,
        sha256="d" * 64,
        size_bytes=2048,
        content_type="application/json; charset=utf-8",
    )

    ready = repository.compare_and_swap(
        analyzing,
        analyzing.manifest.model_copy(
            update={
                "status": AssignmentStatus.READY,
                "physical_ir": physical_ir,
            }
        ),
    )

    with pytest.raises(ValueError, match="physical IR reference is immutable"):
        repository.compare_and_swap(
            ready,
            ready.manifest.model_copy(
                update={"physical_ir": physical_ir.model_copy(update={"generation": 2})}
            ),
        )

    separate = ManifestRepository(LocalObjectStore(tmp_path / "failed-objects"))
    analyzing = separate.create(analyzing_manifest)
    with pytest.raises(ValueError, match="only be attached by the ready transition"):
        separate.compare_and_swap(
            analyzing,
            analyzing.manifest.model_copy(
                update={
                    "status": AssignmentStatus.ANALYSIS_FAILED,
                    "physical_ir": physical_ir,
                }
            ),
        )
