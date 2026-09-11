"""Stable failures shared by local and Google Cloud Storage adapters."""

from __future__ import annotations


class StorageError(RuntimeError):
    pass


class InvalidObjectKey(StorageError, ValueError):
    pass


class ObjectNotFound(StorageError, LookupError):
    pass


class ObjectAlreadyExists(StorageError):
    pass


class GenerationConflict(StorageError):
    pass


class ObjectIntegrityError(StorageError):
    pass


class RangeNotSatisfiable(StorageError, ValueError):
    pass
