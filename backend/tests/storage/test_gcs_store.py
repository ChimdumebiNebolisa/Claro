from __future__ import annotations

from unittest.mock import ANY, MagicMock

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from backend.storage import (
    GCSObjectStore,
    GenerationConflict,
    ObjectAlreadyExists,
    ObjectNotFound,
    parse_byte_range,
)
from backend.storage.gcs import _GENERATION_RETRY, _READ_RETRY


def _store(blob: MagicMock) -> tuple[GCSObjectStore, MagicMock]:
    bucket = MagicMock()
    bucket.name = "private-bucket"
    bucket.blob.return_value = blob
    return GCSObjectStore("private-bucket", bucket=bucket), bucket


def test_gcs_retries_have_an_explicit_total_deadline() -> None:
    assert _READ_RETRY.timeout == 8.0
    assert _GENERATION_RETRY.retry_policy.timeout == 8.0


def test_create_uses_does_not_exist_generation_precondition() -> None:
    blob = MagicMock()
    blob.generation = 9
    store, bucket = _store(blob)

    result = store.create("assignments/a/source.pdf", b"pdf", content_type="application/pdf")

    bucket.blob.assert_called_once_with("assignments/a/source.pdf")
    blob.upload_from_string.assert_called_once_with(
        b"pdf",
        content_type="application/pdf",
        if_generation_match=0,
        timeout=5.0,
        retry=ANY,
    )
    assert blob.metadata == {"claros-sha256": result.sha256}
    assert result.generation == 9


def test_create_maps_gcs_precondition_failure_to_immutable_conflict() -> None:
    blob = MagicMock()
    blob.upload_from_string.side_effect = PreconditionFailed("exists")
    store, _ = _store(blob)

    with pytest.raises(ObjectAlreadyExists):
        store.create("source.pdf", b"pdf", content_type="application/pdf")


def test_cas_and_delete_are_bound_to_exact_generation() -> None:
    blob = MagicMock()
    blob.generation = 12
    store, _ = _store(blob)

    updated = store.compare_and_swap("manifest.json", 11, b"{}", content_type="application/json")
    store.delete("manifest.json", expected_generation=updated.generation)

    blob.upload_from_string.assert_called_once_with(
        b"{}",
        content_type="application/json",
        if_generation_match=11,
        timeout=5.0,
        retry=ANY,
    )
    blob.delete.assert_called_once_with(
        if_generation_match=12,
        timeout=5.0,
        retry=ANY,
    )


def test_cas_and_delete_map_changed_generation() -> None:
    blob = MagicMock()
    blob.upload_from_string.side_effect = PreconditionFailed("stale")
    store, _ = _store(blob)
    with pytest.raises(GenerationConflict):
        store.compare_and_swap("manifest.json", 2, b"{}", content_type="application/json")

    blob.upload_from_string.side_effect = None
    blob.delete.side_effect = PreconditionFailed("stale")
    with pytest.raises(GenerationConflict):
        store.delete("manifest.json", expected_generation=2)


def test_read_and_range_pin_the_observed_generation() -> None:
    blob = MagicMock()
    blob.generation = 4
    blob.size = 10
    blob.content_type = "application/pdf"
    blob.metadata = {
        "claros-sha256": ("84d89877f0d4041efb6bf91a16f0248f2fd573e6af05c19f96bedb9f882f7882")
    }
    blob.download_as_bytes.side_effect = [b"0123456789", b"2345"]
    store, _ = _store(blob)

    complete = store.read("source.pdf")
    selected = store.read_range("source.pdf", parse_byte_range("bytes=2-5", 10))

    assert complete.data == b"0123456789"
    assert selected.data == b"2345"
    assert blob.download_as_bytes.call_args_list[0].kwargs == {
        "if_generation_match": 4,
        "timeout": 5.0,
        "retry": ANY,
    }
    assert blob.download_as_bytes.call_args_list[1].kwargs == {
        "start": 2,
        "end": 5,
        "if_generation_match": 4,
        "timeout": 5.0,
        "retry": ANY,
    }
    assert all(call.kwargs == {"timeout": 5.0, "retry": ANY} for call in blob.reload.call_args_list)


def test_missing_gcs_object_is_non_describing_storage_failure() -> None:
    blob = MagicMock()
    blob.reload.side_effect = NotFound("missing")
    store, _ = _store(blob)

    with pytest.raises(ObjectNotFound, match="does not exist"):
        store.read("unknown.pdf")
