"""Symlink-safe development/test implementation of the object-store contract."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from backend.storage.base import ObjectMetadata, StoredObject, StoredObjectRange
from backend.storage.errors import (
    GenerationConflict,
    ObjectAlreadyExists,
    ObjectIntegrityError,
    ObjectNotFound,
)
from backend.storage.keys import validate_object_key
from backend.storage.ranges import ByteRange

_MAGIC = b"CLAROS-LOCAL-OBJECT-V1\n"
_HEADER_LENGTH_BYTES = 8


class LocalObjectStore:
    """Persist an atomic envelope per object beneath one validated root.

    Local storage is intentionally a development/test adapter. Production uses
    GCS generation preconditions. A per-adapter lock gives deterministic thread
    behavior without pretending the local filesystem is a distributed store.
    """

    def __init__(self, root: Path | str) -> None:
        raw_root = Path(root)
        if raw_root.exists() and raw_root.is_symlink():
            raise ObjectIntegrityError("local storage root cannot be a symlink")
        raw_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if raw_root.is_symlink() or not raw_root.is_dir():
            raise ObjectIntegrityError("local storage root is unsafe")
        self._root = raw_root.resolve(strict=True)
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def create(self, key: str, data: bytes, *, content_type: str) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        payload = _require_bytes(data)
        _validate_content_type(content_type)
        with self._lock:
            target = self._path(safe_key, create_parents=True)
            if target.exists() or target.is_symlink():
                raise ObjectAlreadyExists("the immutable object already exists")
            metadata = _metadata(safe_key, 1, payload, content_type)
            envelope = _encode_envelope(metadata, payload)
            try:
                self._write_exclusive(target, envelope)
            except FileExistsError as exc:
                raise ObjectAlreadyExists("the immutable object already exists") from exc
            return metadata

    def read(self, key: str) -> StoredObject:
        safe_key = validate_object_key(key)
        with self._lock:
            target = self._path(safe_key)
            metadata, data = self._read_envelope(target, safe_key)
            return StoredObject(metadata, data)

    def read_range(self, key: str, byte_range: ByteRange) -> StoredObjectRange:
        stored = self.read(key)
        if byte_range.total_size != stored.metadata.size:
            raise GenerationConflict("the byte range was based on stale object metadata")
        if byte_range.start < 0 or byte_range.end >= stored.metadata.size:
            raise ValueError("byte range falls outside the object")
        return StoredObjectRange(
            stored.metadata,
            byte_range,
            stored.data[byte_range.start : byte_range.end + 1],
        )

    def compare_and_swap(
        self,
        key: str,
        expected_generation: int,
        data: bytes,
        *,
        content_type: str,
    ) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        payload = _require_bytes(data)
        _validate_generation(expected_generation)
        _validate_content_type(content_type)
        with self._lock:
            target = self._path(safe_key)
            current, _ = self._read_envelope(target, safe_key)
            if current.generation != expected_generation:
                raise GenerationConflict("the object changed concurrently")
            updated = _metadata(safe_key, expected_generation + 1, payload, content_type)
            self._atomic_replace(target, _encode_envelope(updated, payload))
            return updated

    def delete(self, key: str, *, expected_generation: int) -> None:
        safe_key = validate_object_key(key)
        _validate_generation(expected_generation)
        with self._lock:
            target = self._path(safe_key)
            current, _ = self._read_envelope(target, safe_key)
            if current.generation != expected_generation:
                raise GenerationConflict("the object changed before deletion")
            target.unlink()

    def _path(self, key: str, *, create_parents: bool = False) -> Path:
        parts = key.split("/")
        current = self._root
        for part in parts[:-1]:
            current = current / part
            if current.exists():
                if current.is_symlink() or not current.is_dir():
                    raise ObjectIntegrityError("local object path traverses unsafe data")
            elif create_parents:
                current.mkdir(mode=0o700)
            else:
                raise ObjectNotFound("the object does not exist")
        target = current / parts[-1]
        try:
            target.relative_to(self._root)
        except ValueError as exc:  # defensive even after closed key validation
            raise ObjectIntegrityError("local object path escaped its root") from exc
        if target.is_symlink():
            raise ObjectIntegrityError("local object target cannot be a symlink")
        return target

    def _read_envelope(self, target: Path, key: str) -> tuple[ObjectMetadata, bytes]:
        if not target.exists():
            raise ObjectNotFound("the object does not exist")
        if target.is_symlink() or not target.is_file():
            raise ObjectIntegrityError("local object target is unsafe")
        try:
            payload = target.read_bytes()
            return _decode_envelope(key, payload)
        except OSError as exc:
            raise ObjectIntegrityError("local object could not be read safely") from exc

    @staticmethod
    def _write_exclusive(target: Path, payload: bytes) -> None:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                target.unlink(missing_ok=True)
            finally:
                raise

    @staticmethod
    def _atomic_replace(target: Path, payload: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".claros-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if target.is_symlink():
                raise ObjectIntegrityError("local object target cannot be a symlink")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _metadata(key: str, generation: int, data: bytes, content_type: str) -> ObjectMetadata:
    return ObjectMetadata(
        key=key,
        generation=generation,
        size=len(data),
        content_type=content_type,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _encode_envelope(metadata: ObjectMetadata, data: bytes) -> bytes:
    header = json.dumps(
        {
            "content_type": metadata.content_type,
            "generation": metadata.generation,
            "sha256": metadata.sha256,
            "size": metadata.size,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return _MAGIC + len(header).to_bytes(_HEADER_LENGTH_BYTES, "big") + header + data


def _decode_envelope(key: str, payload: bytes) -> tuple[ObjectMetadata, bytes]:
    prefix_size = len(_MAGIC) + _HEADER_LENGTH_BYTES
    if len(payload) < prefix_size or not payload.startswith(_MAGIC):
        raise ObjectIntegrityError("local object envelope is invalid")
    header_size = int.from_bytes(payload[len(_MAGIC) : prefix_size], "big")
    if header_size <= 0 or header_size > 4096 or len(payload) < prefix_size + header_size:
        raise ObjectIntegrityError("local object envelope header is invalid")
    try:
        header: Any = json.loads(payload[prefix_size : prefix_size + header_size])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObjectIntegrityError("local object metadata is invalid") from exc
    if not isinstance(header, dict) or set(header) != {
        "content_type",
        "generation",
        "sha256",
        "size",
    }:
        raise ObjectIntegrityError("local object metadata is invalid")
    data = payload[prefix_size + header_size :]
    try:
        metadata = ObjectMetadata(
            key=key,
            generation=int(header["generation"]),
            size=int(header["size"]),
            content_type=str(header["content_type"]),
            sha256=str(header["sha256"]),
        )
    except (TypeError, ValueError) as exc:
        raise ObjectIntegrityError("local object metadata is invalid") from exc
    if metadata.generation < 1 or metadata.size != len(data):
        raise ObjectIntegrityError("local object size or generation is invalid")
    if not hmac.compare_digest(metadata.sha256, hashlib.sha256(data).hexdigest()):
        raise ObjectIntegrityError("local object hash does not match its bytes")
    _validate_content_type(metadata.content_type)
    return metadata, data


def _require_bytes(data: bytes) -> bytes:
    if not isinstance(data, bytes):
        raise TypeError("object data must be bytes")
    return data


def _validate_generation(generation: int) -> None:
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ValueError("expected generation must be a positive integer")


def _validate_content_type(content_type: str) -> None:
    if (
        not isinstance(content_type, str)
        or not content_type
        or len(content_type) > 128
        or any(not 32 <= ord(character) <= 126 for character in content_type)
    ):
        raise ValueError("content type is invalid")
