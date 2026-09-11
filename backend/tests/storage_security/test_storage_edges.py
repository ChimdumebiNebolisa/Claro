from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from google.api_core.exceptions import Conflict, NotFound, PreconditionFailed

from backend.domain.models import ObjectReference
from backend.storage import (
    CreationJournal,
    GCSObjectStore,
    GenerationConflict,
    InvalidObjectKey,
    LocalObjectStore,
    ManifestRepository,
    ObjectAlreadyExists,
    ObjectIntegrityError,
    ObjectMetadata,
    ObjectNotFound,
    StorageError,
    assignment_manifest_object_key,
    deserialize_manifest,
    preview_object_key,
    serialize_manifest,
    validate_object_key,
)
from backend.storage import local as local_module
from backend.storage.manifests import MANIFEST_CONTENT_TYPE
from backend.storage.ranges import ByteRange
from backend.tests.domain.factories import make_manifest

_UNSET = object()


class FakeBlob:
    def __init__(self, payload: bytes = b"data") -> None:
        self.payload = payload
        self.generation: object = 4
        self.size: object = len(payload)
        self.content_type: object = "application/octet-stream"
        self.metadata: object = {"claros-sha256": hashlib.sha256(payload).hexdigest()}
        self.reload_error: Exception | None = None
        self.reload_generation: object = _UNSET
        self.upload_error: Exception | None = None
        self.download_error: Exception | None = None
        self.download_result: bytes | None = None
        self.delete_error: Exception | None = None
        self.reload_count = 0
        self.reload_calls: list[dict[str, Any]] = []
        self.upload_calls: list[tuple[bytes, dict[str, Any]]] = []
        self.download_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []

    def reload(self, **kwargs: Any) -> None:
        self.reload_count += 1
        self.reload_calls.append(kwargs)
        if self.reload_error is not None:
            raise self.reload_error
        if self.reload_generation is not _UNSET:
            self.generation = self.reload_generation

    def upload_from_string(self, payload: bytes, **kwargs: Any) -> None:
        self.upload_calls.append((payload, kwargs))
        if self.upload_error is not None:
            raise self.upload_error

    def download_as_bytes(self, **kwargs: Any) -> bytes:
        self.download_calls.append(kwargs)
        if self.download_error is not None:
            raise self.download_error
        if self.download_result is not None:
            return self.download_result
        if "start" in kwargs:
            return self.payload[kwargs["start"] : kwargs["end"] + 1]
        return self.payload

    def delete(self, **kwargs: Any) -> None:
        self.delete_calls.append(kwargs)
        if self.delete_error is not None:
            raise self.delete_error


class FakeBucket:
    def __init__(self, blob: FakeBlob, *, name: str = "private-bucket") -> None:
        self.name = name
        self._blob = blob
        self.requested_keys: list[str] = []

    def blob(self, key: str) -> FakeBlob:
        self.requested_keys.append(key)
        return self._blob


class FakeClient:
    def __init__(self, bucket: FakeBucket) -> None:
        self._bucket = bucket
        self.requested_names: list[str] = []

    def bucket(self, name: str) -> FakeBucket:
        self.requested_names.append(name)
        return self._bucket


def _gcs_store(blob: FakeBlob) -> GCSObjectStore:
    return GCSObjectStore("private-bucket", bucket=FakeBucket(blob))


def test_gcs_constructor_validates_bucket_source_and_name() -> None:
    blob = FakeBlob()
    bucket = FakeBucket(blob)
    client = FakeClient(bucket)

    with pytest.raises(ValueError, match="bucket name is required"):
        GCSObjectStore("", bucket=bucket)
    with pytest.raises(ValueError, match="bucket name is required"):
        GCSObjectStore(None, bucket=bucket)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="either a GCS client or bucket"):
        GCSObjectStore("private-bucket", client=client, bucket=bucket)
    with pytest.raises(ValueError, match="does not match"):
        GCSObjectStore("private-bucket", bucket=FakeBucket(blob, name="other-bucket"))

    store = GCSObjectStore("private-bucket", client=client)
    assert store._bucket is bucket
    assert client.requested_names == ["private-bucket"]


def test_gcs_create_reloads_missing_generation_and_maps_conflict() -> None:
    blob = FakeBlob()
    blob.generation = None
    blob.reload_generation = 8
    store = _gcs_store(blob)

    metadata = store.create("source.pdf", b"pdf", content_type="application/pdf")

    assert metadata.generation == 8
    assert blob.reload_count == 1
    assert len(blob.upload_calls) == 1
    payload, upload_options = blob.upload_calls[0]
    assert payload == b"pdf"
    assert upload_options["content_type"] == "application/pdf"
    assert upload_options["if_generation_match"] == 0
    assert upload_options["timeout"] == 5.0
    assert "retry" in upload_options
    assert blob.reload_calls[0]["timeout"] == 5.0
    assert "retry" in blob.reload_calls[0]

    blob.upload_error = Conflict("already exists")
    with pytest.raises(ObjectAlreadyExists, match="already exists"):
        store.create("other.pdf", b"pdf", content_type="application/pdf")


def test_gcs_read_backfills_missing_hash_and_default_content_type() -> None:
    blob = FakeBlob(b"source bytes")
    blob.metadata = None
    blob.content_type = None
    stored = _gcs_store(blob).read("source.pdf")

    assert stored.data == b"source bytes"
    assert stored.metadata.content_type == "application/octet-stream"
    assert stored.metadata.sha256 == hashlib.sha256(stored.data).hexdigest()


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("generation", "not-a-generation", "generation is unavailable"),
        ("generation", 0, "generation is invalid"),
        ("size", True, "size metadata is invalid"),
        ("size", -1, "size metadata is invalid"),
        ("metadata", {"claros-sha256": "A" * 64}, "hash metadata is invalid"),
        ("metadata", {"claros-sha256": "abc"}, "hash metadata is invalid"),
    ],
)
def test_gcs_rejects_corrupt_provider_metadata(
    attribute: str,
    value: object,
    message: str,
) -> None:
    blob = FakeBlob()
    setattr(blob, attribute, value)

    with pytest.raises(ObjectIntegrityError, match=message):
        _gcs_store(blob).read("source.pdf")


def test_gcs_rejects_corrupt_object_bytes_and_range_metadata() -> None:
    wrong_size = FakeBlob(b"abc")
    wrong_size.size = 4
    with pytest.raises(ObjectIntegrityError, match="size does not match"):
        _gcs_store(wrong_size).read("source.pdf")

    wrong_hash = FakeBlob(b"abc")
    wrong_hash.metadata = {"claros-sha256": "0" * 64}
    with pytest.raises(ObjectIntegrityError, match="hash does not match"):
        _gcs_store(wrong_hash).read("source.pdf")

    missing_range_hash = FakeBlob(b"abc")
    missing_range_hash.metadata = {}
    with pytest.raises(ObjectIntegrityError, match="missing its authoritative hash"):
        _gcs_store(missing_range_hash).read_range("source.pdf", ByteRange(0, 1, 3))


def test_gcs_range_rejects_stale_bounds_and_truncated_downloads() -> None:
    blob = FakeBlob(b"abcd")
    store = _gcs_store(blob)

    with pytest.raises(GenerationConflict, match="stale object metadata"):
        store.read_range("source.pdf", ByteRange(0, 1, 5))
    with pytest.raises(ValueError, match="outside the object"):
        store.read_range("source.pdf", ByteRange(-1, 1, 4))
    with pytest.raises(ValueError, match="outside the object"):
        store.read_range("source.pdf", ByteRange(1, 4, 4))

    blob.download_result = b"x"
    with pytest.raises(ObjectIntegrityError, match="range length is invalid"):
        store.read_range("source.pdf", ByteRange(0, 1, 4))


def test_gcs_translates_provider_failures_without_leaking_provider_types() -> None:
    blob = FakeBlob()
    store = _gcs_store(blob)

    blob.download_error = PreconditionFailed("stale provider details")
    with pytest.raises(GenerationConflict, match="changed while it was read"):
        store.read("source.pdf")

    blob.download_error = None
    blob.reload_error = NotFound("missing provider details")
    with pytest.raises(ObjectNotFound, match="does not exist"):
        store.read_range("source.pdf", ByteRange(0, 1, 4))

    blob.reload_error = None
    blob.upload_error = NotFound("missing provider details")
    with pytest.raises(GenerationConflict, match="changed concurrently"):
        store.compare_and_swap(
            "manifest.json",
            4,
            b"{}",
            content_type="application/json",
        )

    blob.upload_error = None
    blob.delete_error = NotFound("missing provider details")
    with pytest.raises(ObjectNotFound, match="does not exist"):
        store.delete("manifest.json", expected_generation=4)

    blob.delete_error = PreconditionFailed("stale provider details")
    with pytest.raises(GenerationConflict, match="changed before deletion"):
        store.delete("manifest.json", expected_generation=4)


def test_gcs_validates_payload_generation_and_content_type_before_provider_use() -> None:
    store = _gcs_store(FakeBlob())

    with pytest.raises(TypeError, match="data must be bytes"):
        store.create("source.pdf", bytearray(b"pdf"), content_type="application/pdf")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="content type is invalid"):
        store.create("source.pdf", b"pdf", content_type="")
    with pytest.raises(ValueError, match="positive integer"):
        store.compare_and_swap("manifest.json", True, b"{}", content_type="application/json")


@pytest.mark.parametrize("key", [None, "", "a" * 513, "hidden/.object"])
def test_object_key_boundary_validation(key: str | None) -> None:
    with pytest.raises(InvalidObjectKey):
        validate_object_key(key)  # type: ignore[arg-type]


@pytest.mark.parametrize("page_number", [True, 0, 9])
def test_preview_key_rejects_non_page_boundaries(page_number: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 8"):
        preview_object_key("asg_test_01", page_number)


def _raw_envelope(header: object, data: bytes = b"abc") -> bytes:
    encoded_header = json.dumps(header, separators=(",", ":")).encode("utf-8")
    return (
        local_module._MAGIC
        + len(encoded_header).to_bytes(local_module._HEADER_LENGTH_BYTES, "big")
        + encoded_header
        + data
    )


def test_local_store_classifies_corrupt_envelopes_as_integrity_failures(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    digest = hashlib.sha256(b"abc").hexdigest()
    valid = {
        "content_type": "application/octet-stream",
        "generation": 1,
        "sha256": digest,
        "size": 3,
    }
    corrupt_payloads = [
        b"not-an-envelope",
        local_module._MAGIC + (0).to_bytes(local_module._HEADER_LENGTH_BYTES, "big"),
        local_module._MAGIC + (1).to_bytes(local_module._HEADER_LENGTH_BYTES, "big") + b"{",
        _raw_envelope(["not", "metadata"]),
        _raw_envelope({**valid, "generation": "not-an-integer"}),
        _raw_envelope({**valid, "generation": 0}),
        _raw_envelope({**valid, "size": 4}),
        _raw_envelope({**valid, "sha256": "0" * 64}),
    ]

    for index, payload in enumerate(corrupt_payloads):
        key = f"corrupt/object-{index}.bin"
        target = store.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        with pytest.raises(ObjectIntegrityError):
            store.read(key)


def test_local_store_rejects_unsafe_paths_and_range_boundaries(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    (store.root / "unsafe-parent").write_text("not a directory", encoding="utf-8")
    with pytest.raises(ObjectIntegrityError, match="unsafe data"):
        store.read("unsafe-parent/object.bin")

    (store.root / "directory-target").mkdir()
    with pytest.raises(ObjectIntegrityError, match="target is unsafe"):
        store.read("directory-target")
    with pytest.raises(ObjectNotFound):
        store.read("missing/child.bin")

    metadata = store.create("source.pdf", b"abcd", content_type="application/pdf")
    with pytest.raises(ValueError, match="outside the object"):
        store.read_range(metadata.key, ByteRange(-1, 1, metadata.size))
    with pytest.raises(ValueError, match="outside the object"):
        store.read_range(metadata.key, ByteRange(1, metadata.size, metadata.size))


def test_local_store_maps_exclusive_create_race_and_validates_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalObjectStore(tmp_path / "objects")

    def concurrent_create(*_args: object, **_kwargs: object) -> int:
        raise FileExistsError

    monkeypatch.setattr(local_module.os, "open", concurrent_create)
    with pytest.raises(ObjectAlreadyExists):
        store.create("race.bin", b"data", content_type="application/octet-stream")

    with pytest.raises(TypeError, match="data must be bytes"):
        store.create("invalid.bin", bytearray(b"data"), content_type="application/pdf")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="content type is invalid"):
        store.create("invalid.bin", b"data", content_type="bad\ncontent-type")
    with pytest.raises(ValueError, match="positive integer"):
        store.delete("invalid.bin", expected_generation=False)


def test_manifest_repository_rejects_binding_corruption_and_invalid_payloads(
    tmp_path: Path,
) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    repository = ManifestRepository(store)
    manifest = make_manifest()
    store.create(
        assignment_manifest_object_key("asg_other_01"),
        serialize_manifest(manifest),
        content_type=MANIFEST_CONTENT_TYPE,
    )

    with pytest.raises(ObjectIntegrityError, match="assignment binding"):
        repository.load("asg_other_01")
    with pytest.raises(TypeError, match="payload must be bytes"):
        deserialize_manifest("{}")  # type: ignore[arg-type]
    with pytest.raises(ObjectIntegrityError, match="manifest is invalid"):
        deserialize_manifest(b"{}")


def test_manifest_transition_preserves_every_immutable_binding(tmp_path: Path) -> None:
    repository = ManifestRepository(LocalObjectStore(tmp_path / "objects"))
    observed = repository.create(make_manifest(version=2))
    manifest = observed.manifest
    physical_ir = ObjectReference(
        key="assignments/asg_test_01/analysis/physical-ir.json",
        generation=1,
        sha256="d" * 64,
        size_bytes=256,
        content_type="application/json",
    )
    invalid_updates = [
        (manifest.model_copy(update={"assignment_id": "asg_other_01"}), "assignment_id"),
        (manifest.model_copy(update={"owner_hash": "b" * 64}), "owner binding"),
        (
            manifest.model_copy(
                update={"source": manifest.source.model_copy(update={"generation": 8})}
            ),
            "source reference",
        ),
        (manifest.model_copy(update={"physical_ir": physical_ir}), "physical IR reference"),
        (manifest.model_copy(update={"source_filename": "renamed.pdf"}), "source filename"),
        (
            manifest.model_copy(update={"created_at": manifest.created_at.replace(microsecond=1)}),
            "absolute lifetime",
        ),
        (manifest.model_copy(update={"version": 1}), "public version cannot decrease"),
    ]

    for updated, message in invalid_updates:
        with pytest.raises(ValueError, match=message):
            repository.compare_and_swap(observed, updated)


class FakeDeleteStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def delete(self, key: str, *, expected_generation: int) -> None:
        self.calls.append((key, expected_generation))
        if key == "request/missing.bin":
            raise ObjectNotFound("missing")
        if key == "request/replaced.bin":
            raise GenerationConflict("replaced")
        if key == "request/provider.bin":
            raise StorageError("provider unavailable")


def test_creation_journal_is_immutable_to_callers_and_collects_cleanup_failures() -> None:
    journal = CreationJournal()
    for index, key in enumerate(
        [
            "request/first.bin",
            "request/missing.bin",
            "request/replaced.bin",
            "request/provider.bin",
        ],
        start=1,
    ):
        journal.record(ObjectMetadata(key, index, 1, "application/octet-stream", "a" * 64))
    snapshot = journal.objects
    store = FakeDeleteStore()

    failures = journal.cleanup(store)  # type: ignore[arg-type]

    assert snapshot == journal.objects
    assert store.calls == [
        ("request/provider.bin", 4),
        ("request/replaced.bin", 3),
        ("request/missing.bin", 2),
        ("request/first.bin", 1),
    ]
    assert [str(error) for error in failures] == ["provider unavailable"]
