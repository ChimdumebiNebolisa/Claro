from __future__ import annotations

import pytest

from backend.domain.errors import NoConfirmedAnswers
from backend.domain.models import ExportStatus, ObjectReference
from backend.domain.workflow import (
    complete_export,
    fail_export,
    start_export,
)
from backend.tests.domain.conftest import NOW


def test_export_requires_at_least_one_confirmed_answer(manifest_factory) -> None:
    manifest = manifest_factory()
    with pytest.raises(NoConfirmedAnswers):
        start_export(
            manifest,
            assignment_version=manifest.version,
            idempotency_key="0123456789abcdef",
            now=NOW,
        )
    assert manifest.exports == ()


def test_one_assignment_version_has_one_export_identity(reviewed_manifest) -> None:
    from backend.tests.domain.test_confirmation_workflow import _confirm

    confirmed = _confirm(reviewed_manifest).manifest
    first = start_export(
        confirmed,
        assignment_version=confirmed.version,
        idempotency_key="0123456789abcdef",
        now=NOW,
    )
    replay = start_export(
        first.manifest,
        assignment_version=confirmed.version,
        idempotency_key="fedcba9876543210",
        now=NOW,
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.export.export_id == first.export.export_id
    assert replay.manifest.version == confirmed.version
    assert len(replay.manifest.exports) == 1


def test_failed_export_retries_same_identity_and_complete_export_is_immutable(
    reviewed_manifest,
) -> None:
    from backend.tests.domain.test_confirmation_workflow import _confirm

    confirmed = _confirm(reviewed_manifest).manifest
    started = start_export(
        confirmed,
        assignment_version=confirmed.version,
        idempotency_key="0123456789abcdef",
        now=NOW,
    )
    failed_manifest, failed = fail_export(
        started.manifest,
        export_id=started.export.export_id,
        failure_code="render_failed",
    )
    retried = start_export(
        failed_manifest,
        assignment_version=confirmed.version,
        idempotency_key="0123456789abcdef",
        now=NOW,
    )
    assert retried.export.export_id == failed.export_id
    assert retried.export.status == ExportStatus.CREATING

    pdf_ref = ObjectReference(
        key=f"assignments/asg_test_01/exports/{failed.export_id}/completed.pdf",
        generation=1,
        sha256="1" * 64,
        size_bytes=2048,
        content_type="application/pdf",
    )
    manifest_ref = ObjectReference(
        key=f"assignments/asg_test_01/exports/{failed.export_id}/manifest.json",
        generation=1,
        sha256="2" * 64,
        size_bytes=512,
        content_type="application/json",
    )
    completed_manifest, completed = complete_export(
        retried.manifest,
        export_id=failed.export_id,
        object_ref=pdf_ref,
        manifest_ref=manifest_ref,
    )
    assert completed.status == ExportStatus.COMPLETE
    assert completed.object_ref == pdf_ref
    assert completed_manifest.source == confirmed.source
    assert completed_manifest.version == confirmed.version
