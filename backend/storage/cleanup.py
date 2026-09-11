"""Request-scoped cleanup that cannot delete objects it did not create."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.storage.base import ObjectMetadata, ObjectStore
from backend.storage.errors import GenerationConflict, ObjectNotFound, StorageError


@dataclass(frozen=True, slots=True)
class CreatedObject:
    key: str
    generation: int


@dataclass(slots=True)
class CreationJournal:
    """Track exact generations created by one request for safe rollback."""

    _objects: list[CreatedObject] = field(default_factory=list)

    def record(self, metadata: ObjectMetadata) -> ObjectMetadata:
        self._objects.append(CreatedObject(metadata.key, metadata.generation))
        return metadata

    @property
    def objects(self) -> tuple[CreatedObject, ...]:
        return tuple(self._objects)

    def cleanup(self, store: ObjectStore) -> tuple[StorageError, ...]:
        """Best-effort rollback in reverse order, always generation-bound."""

        failures: list[StorageError] = []
        for item in reversed(self._objects):
            try:
                store.delete(item.key, expected_generation=item.generation)
            except (ObjectNotFound, GenerationConflict):
                # Missing or replaced data is no longer this request's exact object.
                continue
            except StorageError as exc:
                failures.append(exc)
        return tuple(failures)
