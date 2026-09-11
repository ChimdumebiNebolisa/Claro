"""Private Google Cloud Storage adapter using exact generation preconditions."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from google.api_core.exceptions import Conflict, NotFound, PreconditionFailed
from google.cloud.storage import Client
from google.cloud.storage.retry import (
    DEFAULT_RETRY,
    ConditionalRetryPolicy,
    is_generation_specified,
)

from backend.storage.base import ObjectMetadata, StoredObject, StoredObjectRange
from backend.storage.errors import (
    GenerationConflict,
    ObjectAlreadyExists,
    ObjectIntegrityError,
    ObjectNotFound,
)
from backend.storage.keys import validate_object_key
from backend.storage.ranges import ByteRange

_SHA256_METADATA_KEY = "claros-sha256"
_RPC_TIMEOUT_SECONDS = 5.0
_RETRY_TIMEOUT_SECONDS = 8.0
_READ_RETRY = DEFAULT_RETRY.with_timeout(_RETRY_TIMEOUT_SECONDS)
_GENERATION_RETRY = ConditionalRetryPolicy(
    _READ_RETRY,
    is_generation_specified,
    ["query_params"],
)


class GCSObjectStore:
    """Object-store implementation with no public URL or unguarded overwrite seam."""

    def __init__(
        self,
        bucket_name: str,
        *,
        client: Client | None = None,
        bucket: Any | None = None,
    ) -> None:
        if not isinstance(bucket_name, str) or not bucket_name:
            raise ValueError("GCS bucket name is required")
        if bucket is not None and client is not None:
            raise ValueError("provide either a GCS client or bucket, not both")
        self._bucket = bucket or (client or Client()).bucket(bucket_name)
        if getattr(self._bucket, "name", bucket_name) != bucket_name:
            raise ValueError("GCS bucket does not match configured bucket name")

    def create(self, key: str, data: bytes, *, content_type: str) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        payload = _require_bytes(data)
        _validate_content_type(content_type)
        blob = self._bucket.blob(safe_key)
        digest = hashlib.sha256(payload).hexdigest()
        blob.metadata = {_SHA256_METADATA_KEY: digest}
        try:
            blob.upload_from_string(
                payload,
                content_type=content_type,
                if_generation_match=0,
                timeout=_RPC_TIMEOUT_SECONDS,
                retry=_GENERATION_RETRY,
            )
            _ensure_loaded_generation(blob)
        except (Conflict, PreconditionFailed) as exc:
            raise ObjectAlreadyExists("the immutable object already exists") from exc
        return ObjectMetadata(
            key=safe_key,
            generation=_blob_generation(blob),
            size=len(payload),
            content_type=content_type,
            sha256=digest,
        )

    def read(self, key: str) -> StoredObject:
        safe_key = validate_object_key(key)
        blob = self._bucket.blob(safe_key)
        try:
            blob.reload(timeout=_RPC_TIMEOUT_SECONDS, retry=_READ_RETRY)
            metadata = _metadata_from_blob(safe_key, blob, require_sha=False)
            data = blob.download_as_bytes(
                if_generation_match=metadata.generation,
                timeout=_RPC_TIMEOUT_SECONDS,
                retry=_GENERATION_RETRY,
            )
        except NotFound as exc:
            raise ObjectNotFound("the object does not exist") from exc
        except PreconditionFailed as exc:
            raise GenerationConflict("the object changed while it was read") from exc
        digest = hashlib.sha256(data).hexdigest()
        if metadata.size != len(data):
            raise ObjectIntegrityError("the stored object size does not match its bytes")
        if metadata.sha256 and not hmac.compare_digest(metadata.sha256, digest):
            raise ObjectIntegrityError("the stored object hash does not match its bytes")
        if not metadata.sha256:
            metadata = ObjectMetadata(
                key=metadata.key,
                generation=metadata.generation,
                size=metadata.size,
                content_type=metadata.content_type,
                sha256=digest,
            )
        return StoredObject(metadata, data)

    def read_range(self, key: str, byte_range: ByteRange) -> StoredObjectRange:
        safe_key = validate_object_key(key)
        blob = self._bucket.blob(safe_key)
        try:
            blob.reload(timeout=_RPC_TIMEOUT_SECONDS, retry=_READ_RETRY)
            metadata = _metadata_from_blob(safe_key, blob, require_sha=True)
            if byte_range.total_size != metadata.size:
                raise GenerationConflict("the byte range was based on stale object metadata")
            if byte_range.start < 0 or byte_range.end >= metadata.size:
                raise ValueError("byte range falls outside the object")
            data = blob.download_as_bytes(
                start=byte_range.start,
                end=byte_range.end,
                if_generation_match=metadata.generation,
                timeout=_RPC_TIMEOUT_SECONDS,
                retry=_GENERATION_RETRY,
            )
        except NotFound as exc:
            raise ObjectNotFound("the object does not exist") from exc
        except PreconditionFailed as exc:
            raise GenerationConflict("the object changed while it was read") from exc
        if len(data) != byte_range.length:
            raise ObjectIntegrityError("the stored range length is invalid")
        return StoredObjectRange(metadata, byte_range, data)

    def compare_and_swap(
        self,
        key: str,
        expected_generation: int,
        data: bytes,
        *,
        content_type: str,
    ) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        _validate_generation(expected_generation)
        payload = _require_bytes(data)
        _validate_content_type(content_type)
        blob = self._bucket.blob(safe_key)
        digest = hashlib.sha256(payload).hexdigest()
        blob.metadata = {_SHA256_METADATA_KEY: digest}
        try:
            blob.upload_from_string(
                payload,
                content_type=content_type,
                if_generation_match=expected_generation,
                timeout=_RPC_TIMEOUT_SECONDS,
                retry=_GENERATION_RETRY,
            )
            _ensure_loaded_generation(blob)
        except (NotFound, PreconditionFailed) as exc:
            raise GenerationConflict("the object changed concurrently") from exc
        return ObjectMetadata(
            key=safe_key,
            generation=_blob_generation(blob),
            size=len(payload),
            content_type=content_type,
            sha256=digest,
        )

    def delete(self, key: str, *, expected_generation: int) -> None:
        safe_key = validate_object_key(key)
        _validate_generation(expected_generation)
        blob = self._bucket.blob(safe_key)
        try:
            blob.delete(
                if_generation_match=expected_generation,
                timeout=_RPC_TIMEOUT_SECONDS,
                retry=_GENERATION_RETRY,
            )
        except NotFound as exc:
            raise ObjectNotFound("the object does not exist") from exc
        except PreconditionFailed as exc:
            raise GenerationConflict("the object changed before deletion") from exc


def _metadata_from_blob(key: str, blob: Any, *, require_sha: bool) -> ObjectMetadata:
    generation = _blob_generation(blob)
    size = getattr(blob, "size", None)
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ObjectIntegrityError("GCS object size metadata is invalid")
    content_type = getattr(blob, "content_type", None) or "application/octet-stream"
    custom = getattr(blob, "metadata", None) or {}
    digest = custom.get(_SHA256_METADATA_KEY, "")
    if digest and (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ObjectIntegrityError("GCS object hash metadata is invalid")
    if require_sha and not digest:
        raise ObjectIntegrityError("GCS object is missing its authoritative hash")
    return ObjectMetadata(key, generation, size, content_type, digest)


def _ensure_loaded_generation(blob: Any) -> None:
    if getattr(blob, "generation", None) is None:
        blob.reload(timeout=_RPC_TIMEOUT_SECONDS, retry=_READ_RETRY)


def _blob_generation(blob: Any) -> int:
    raw = getattr(blob, "generation", None)
    try:
        generation = int(raw)
    except (TypeError, ValueError) as exc:
        raise ObjectIntegrityError("GCS object generation is unavailable") from exc
    if generation < 1:
        raise ObjectIntegrityError("GCS object generation is invalid")
    return generation


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
