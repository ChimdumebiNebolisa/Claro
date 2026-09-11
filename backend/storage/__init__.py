"""Durable object storage and manifest persistence for Claros V2."""

from backend.storage.base import (
    ObjectMetadata,
    ObjectStore,
    StoredObject,
    StoredObjectRange,
)
from backend.storage.cleanup import CreatedObject, CreationJournal
from backend.storage.errors import (
    GenerationConflict,
    InvalidObjectKey,
    ObjectAlreadyExists,
    ObjectIntegrityError,
    ObjectNotFound,
    RangeNotSatisfiable,
    StorageError,
)
from backend.storage.gcs import GCSObjectStore
from backend.storage.keys import (
    assignment_manifest_object_key,
    assignment_prefix,
    export_manifest_object_key,
    export_pdf_object_key,
    physical_ir_object_key,
    preview_object_key,
    source_object_key,
    validate_object_key,
)
from backend.storage.local import LocalObjectStore
from backend.storage.manifests import (
    MANIFEST_CONTENT_TYPE,
    ManifestRepository,
    VersionedManifest,
    deserialize_manifest,
    serialize_manifest,
)
from backend.storage.ranges import ByteRange, parse_byte_range

__all__ = [
    "MANIFEST_CONTENT_TYPE",
    "ByteRange",
    "CreatedObject",
    "CreationJournal",
    "GCSObjectStore",
    "GenerationConflict",
    "InvalidObjectKey",
    "LocalObjectStore",
    "ManifestRepository",
    "ObjectAlreadyExists",
    "ObjectIntegrityError",
    "ObjectMetadata",
    "ObjectNotFound",
    "ObjectStore",
    "RangeNotSatisfiable",
    "StorageError",
    "StoredObject",
    "StoredObjectRange",
    "VersionedManifest",
    "assignment_manifest_object_key",
    "assignment_prefix",
    "deserialize_manifest",
    "export_manifest_object_key",
    "export_pdf_object_key",
    "parse_byte_range",
    "physical_ir_object_key",
    "preview_object_key",
    "serialize_manifest",
    "source_object_key",
    "validate_object_key",
]
