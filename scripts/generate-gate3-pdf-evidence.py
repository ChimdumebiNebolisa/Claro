"""Generate the deterministic Gate 3 inline-plus-appendix inspection PDF."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pikepdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.document import (  # noqa: E402 - repository script bootstrap.
    ConfirmedAnswerForExport,
    PreflightLimits,
    QuestionEvidence,
    build_export,
    extract_physical_ir,
    resolve_placement,
)
from backend.document_execution import ground_questions  # noqa: E402

SOURCE = ROOT / "backend" / "tests" / "corpus" / "01-biology-polished.pdf"
OUTPUT_DIR = ROOT / "artifacts" / "v2" / "gate3"
OUTPUT_PDF = OUTPUT_DIR / "completed-inline-appendix.pdf"
OUTPUT_MANIFEST = OUTPUT_DIR / "completed-inline-appendix.manifest.json"

SHORT_ANSWER = "Mitochondria release usable energy from food — exactly as reviewed."
LONG_ANSWER = (
    "Chloroplasts capture sunlight so plant cells can make food from water and carbon dioxide. "
    * 36
).strip()


def build_evidence() -> tuple[bytes, bytes]:
    source = SOURCE.read_bytes()
    physical = extract_physical_ir(source)
    questions = ground_questions(physical, limits=PreflightLimits())
    if len(questions) != 2:
        raise RuntimeError("the pinned biology fixture must contain exactly two questions")

    plans = []
    answers = []
    for question, exact_text in zip(questions, (SHORT_ANSWER, LONG_ANSWER), strict=True):
        evidence = QuestionEvidence(
            question_id=question.question_id,
            display_identifier=question.display_identifier,
            prompt_block_ids=question.prompt_block_ids,
            context_block_ids=question.context_block_ids,
        )
        plan = resolve_placement(
            physical,
            evidence,
            exact_text,
            occupied_plans=tuple(plans),
        )
        plans.append(plan)
        answers.append(
            ConfirmedAnswerForExport(
                question_id=question.question_id,
                display_identifier=question.display_identifier,
                prompt_block_ids=question.prompt_block_ids,
                context_block_ids=question.context_block_ids,
                exact_text=exact_text,
                reviewed_placement_hash=plan.placement_hash,
            )
        )

    if [plan.outcome for plan in plans] != ["inline", "appendix"]:
        raise RuntimeError("the Gate 3 inspection fixture must prove inline and appendix output")
    first = build_export(
        source,
        physical,
        "Gate 3 biology inspection worksheet",
        tuple(answers),
    )
    second = build_export(
        source,
        physical,
        "Gate 3 biology inspection worksheet",
        tuple(answers),
    )
    if first.pdf_bytes != second.pdf_bytes:
        raise RuntimeError("Gate 3 inspection PDF generation is not byte deterministic")
    if first.manifest.canonical_bytes() != second.manifest.canonical_bytes():
        raise RuntimeError("Gate 3 inspection manifest generation is not deterministic")
    with pikepdf.Pdf.open(io.BytesIO(first.pdf_bytes), attempt_recovery=False) as checked:
        if len(checked.pages) != first.manifest.output_page_count:
            raise RuntimeError("Gate 3 inspection PDF page count is invalid")
    return first.pdf_bytes, first.manifest.canonical_bytes()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pdf_bytes, manifest_bytes = build_evidence()

    if args.check:
        if not OUTPUT_PDF.is_file() or OUTPUT_PDF.read_bytes() != pdf_bytes:
            raise SystemExit("Gate 3 PDF evidence is missing or stale")
        if not OUTPUT_MANIFEST.is_file() or OUTPUT_MANIFEST.read_bytes() != manifest_bytes:
            raise SystemExit("Gate 3 manifest evidence is missing or stale")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not OUTPUT_PDF.is_file() or OUTPUT_PDF.read_bytes() != pdf_bytes:
        OUTPUT_PDF.write_bytes(pdf_bytes)
    if not OUTPUT_MANIFEST.is_file() or OUTPUT_MANIFEST.read_bytes() != manifest_bytes:
        OUTPUT_MANIFEST.write_bytes(manifest_bytes)


if __name__ == "__main__":
    main()
