# ruff: noqa: S101

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _runner():
    spec = importlib.util.spec_from_file_location(
        "openpdf_validation_evidence", ROOT / "run-evidence.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summary_reports_mean_p50_nearest_rank_p95_and_max() -> None:
    module = _runner()
    rows = [
        {
            "sample_ms": value,
            "pdfbox_profile": {
                "phases_ms": {"rendering_ms": value / 2},
                "validator_internal_total_ms": value,
                "jvm_process_overhead_ms": 1.0,
            },
        }
        for value in range(1, 11)
    ]
    result = module.summarize(rows)
    assert result["metrics"]["sample_ms"] == {"mean": 6, "p50": 6, "p95": 10, "max": 10}
    assert result["pdfbox_profile_mean_ms"]["rendering_ms"] == 2.75


def test_checked_in_evidence_covers_required_defects_and_all_validators() -> None:
    evidence = json.loads((ROOT / "evidence.json").read_text(encoding="utf-8"))
    rows = {row["case"]: row for row in evidence["differential"]["cases"]}
    required = {
        "malformed_structure",
        "ligature_bad_tounicode",
        "wrong_generated_text",
        "missing_generated_text",
        "incorrect_physical_coordinates",
        "page_box_mutation",
        "page_rotation_mutation",
        "source_content_stream_mutation",
        "annotation_mutation",
        "form_mutation",
        "link_mutation",
        "outline_mutation",
        "continuation_ordering_error",
        "continuation_text_error",
        "valid_pdf_wrong_committed_answer",
        "untouched_source_returned",
    }
    assert required <= rows.keys()
    assert all(set(row["validators"]) == {"qpdf", "pdfbox", "pdfjs"} for row in rows.values())
    assert all(
        not row["validators"]["pdfbox"]["accepted"]
        for row in rows.values()
        if row["expected"] == "reject"
    )


def test_checked_in_benchmarks_have_ten_sequential_runs_per_gate() -> None:
    evidence = json.loads((ROOT / "evidence.json").read_text(encoding="utf-8"))
    variants = evidence["validation_variants"]
    assert set(variants) == {"full", "qpdf_pdfbox", "pdfbox_only"}
    assert all(
        item["summary"]["jobs"] == 10 and len(item["runs"]) == 10 for item in variants.values()
    )
    assert set(evidence["document_sizes"]) == {"small", "medium", "large"}
