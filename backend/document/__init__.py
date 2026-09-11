"""Deterministic, server-authoritative PDF analysis and export."""

from backend.document.errors import DocumentEngineError
from backend.document.exporter import (
    ConfirmedAnswerForExport,
    ExportArtifact,
    build_export,
    publish_validated_export,
)
from backend.document.geometry import (
    PlacementPlan,
    QuestionEvidence,
    parse_placement_plan,
    resolve_placement,
    validate_placement_plan,
)
from backend.document.physical_ir import extract_physical_ir, parse_physical_ir
from backend.document.preflight import PreflightLimits, preflight_pdf

__all__ = [
    "ConfirmedAnswerForExport",
    "DocumentEngineError",
    "ExportArtifact",
    "PlacementPlan",
    "PreflightLimits",
    "QuestionEvidence",
    "build_export",
    "extract_physical_ir",
    "parse_physical_ir",
    "parse_placement_plan",
    "preflight_pdf",
    "publish_validated_export",
    "resolve_placement",
    "validate_placement_plan",
]
