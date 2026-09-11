"""Narrow immutable/CAS object-store interface used by the V2 service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.storage.ranges import ByteRange


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    key: str
    generation: int
    size: int
    content_type: str
    sha256: str


@dataclass(frozen=True, slots=True)
class StoredObject:
    metadata: ObjectMetadata
    data: bytes


@dataclass(frozen=True, slots=True)
class StoredObjectRange:
    metadata: ObjectMetadata
    byte_range: ByteRange
    data: bytes


class ObjectStore(Protocol):
    """No unguarded overwrite or delete operation exists by design."""

    def create(self, key: str, data: bytes, *, content_type: str) -> ObjectMetadata: ...

    def read(self, key: str) -> StoredObject: ...

    def read_range(self, key: str, byte_range: ByteRange) -> StoredObjectRange: ...

    def compare_and_swap(
        self,
        key: str,
        expected_generation: int,
        data: bytes,
        *,
        content_type: str,
    ) -> ObjectMetadata: ...

    def delete(self, key: str, *, expected_generation: int) -> None: ...
