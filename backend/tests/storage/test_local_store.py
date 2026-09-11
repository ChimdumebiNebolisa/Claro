from __future__ import annotations

import threading
from pathlib import Path

import pytest

from backend.storage import (
    CreationJournal,
    GenerationConflict,
    LocalObjectStore,
    ObjectAlreadyExists,
    ObjectIntegrityError,
    ObjectNotFound,
    parse_byte_range,
)


def test_immutable_create_read_and_exact_generation_delete(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    created = store.create("fixtures/source.pdf", b"%PDF-fixture", content_type="application/pdf")

    assert created.generation == 1
    assert store.read(created.key).data == b"%PDF-fixture"
    with pytest.raises(ObjectAlreadyExists):
        store.create(created.key, b"replacement", content_type="application/pdf")
    with pytest.raises(GenerationConflict):
        store.delete(created.key, expected_generation=2)
    assert store.read(created.key).data == b"%PDF-fixture"

    store.delete(created.key, expected_generation=1)
    with pytest.raises(ObjectNotFound):
        store.read(created.key)


def test_range_read_uses_exact_object_metadata(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    metadata = store.create("source.pdf", b"0123456789", content_type="application/pdf")
    byte_range = parse_byte_range("bytes=3-7", metadata.size)

    result = store.read_range(metadata.key, byte_range)

    assert result.data == b"34567"
    assert result.byte_range.content_range == "bytes 3-7/10"
    stale = parse_byte_range("bytes=0-1", 11)
    with pytest.raises(GenerationConflict):
        store.read_range(metadata.key, stale)


def test_compare_and_swap_increments_generation_even_for_identical_bytes(
    tmp_path: Path,
) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    created = store.create("manifest.json", b"{}", content_type="application/json")
    updated = store.compare_and_swap(
        created.key,
        created.generation,
        b"{}",
        content_type="application/json",
    )

    assert updated.generation == created.generation + 1
    with pytest.raises(GenerationConflict):
        store.compare_and_swap(
            created.key,
            created.generation,
            b"{}",
            content_type="application/json",
        )


def test_two_manifest_writers_using_one_generation_have_one_winner(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    created = store.create("manifest.json", b"v1", content_type="application/json")
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def write(payload: bytes) -> None:
        barrier.wait(timeout=2)
        try:
            store.compare_and_swap(
                created.key,
                created.generation,
                payload,
                content_type="application/json",
            )
            outcomes.append("ok")
        except GenerationConflict:
            outcomes.append("conflict")

    threads = [
        threading.Thread(target=write, args=(payload,)) for payload in (b"writer-a", b"writer-b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["conflict", "ok"]
    assert store.read(created.key).data in {b"writer-a", b"writer-b"}


def test_symlink_root_parent_and_target_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root_link = tmp_path / "root-link"
    try:
        root_link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(ObjectIntegrityError):
        LocalObjectStore(root_link)

    root = tmp_path / "safe-root"
    store = LocalObjectStore(root)
    (root / "assignments").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ObjectIntegrityError):
        store.create("assignments/source.pdf", b"unsafe", content_type="application/pdf")

    (root / "assignments").unlink()
    (root / "assignments").mkdir()
    target = root / "assignments" / "source.pdf"
    target.symlink_to(Path(__file__))
    with pytest.raises(ObjectIntegrityError):
        store.read("assignments/source.pdf")


def test_cleanup_deletes_only_exact_generations_created_by_request(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    journal = CreationJournal()
    exact = journal.record(
        store.create("request/exact.bin", b"exact", content_type="application/octet-stream")
    )
    changed = journal.record(
        store.create("request/changed.bin", b"old", content_type="application/octet-stream")
    )
    unrelated = store.create("other/keep.bin", b"keep", content_type="application/octet-stream")
    store.compare_and_swap(
        changed.key,
        changed.generation,
        b"new-owner",
        content_type="application/octet-stream",
    )

    assert journal.cleanup(store) == ()
    with pytest.raises(ObjectNotFound):
        store.read(exact.key)
    assert store.read(changed.key).data == b"new-owner"
    assert store.read(unrelated.key).data == b"keep"
