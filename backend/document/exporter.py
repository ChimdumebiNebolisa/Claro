"""Immutable-source export orchestration and validation."""

from __future__ import annotations

import hmac
import io
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Generic, TypeVar

import pikepdf
from pypdf import PdfReader

from backend.document.errors import DocumentEngineError, document_error
from backend.document.geometry import (
    MIN_FONT_SIZE_MPT,
    PlacementPlan,
    QuestionEvidence,
    resolve_placement,
)
from backend.document.models import PhysicalDocumentIR, canonical_json_bytes, sha256_hex
from backend.document.physical_ir import extract_physical_ir
from backend.document.renderer import (
    AppendixEntry,
    AppendixRenderResult,
    assemble_derivative,
    render_appendix,
)

EXPORTER_VERSION = "claros-export-v2.0.0"


@dataclass(frozen=True, slots=True)
class ConfirmedAnswerForExport:
    question_id: str
    display_identifier: str
    prompt_block_ids: tuple[str, ...]
    context_block_ids: tuple[str, ...]
    exact_text: str
    reviewed_placement_hash: str

    def __post_init__(self) -> None:
        if not self.question_id or not self.display_identifier or not self.exact_text:
            raise document_error("invalid_export")
        if len(self.reviewed_placement_hash) != 64:
            raise document_error("invalid_export")

    def question_evidence(self) -> QuestionEvidence:
        return QuestionEvidence(
            question_id=self.question_id,
            display_identifier=self.display_identifier,
            prompt_block_ids=self.prompt_block_ids,
            context_block_ids=self.context_block_ids,
            grounded=True,
        )


@dataclass(frozen=True, slots=True)
class ExportAnswerManifest:
    question_id: str
    exact_question_sha256: str
    exact_text_sha256: str
    placement_hash: str
    outcome: str
    source_page_number: int
    font_size_mpt: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "question_id": self.question_id,
            "exact_question_sha256": self.exact_question_sha256,
            "exact_text_sha256": self.exact_text_sha256,
            "placement_hash": self.placement_hash,
            "outcome": self.outcome,
            "source_page_number": self.source_page_number,
            "font_size_mpt": self.font_size_mpt,
        }


@dataclass(frozen=True, slots=True)
class DocumentExportManifest:
    exporter_version: str
    source_sha256: str
    physical_ir_sha256: str
    worksheet_title_sha256: str
    source_page_count: int
    appendix_page_count: int
    output_page_count: int
    output_sha256: str
    answers: tuple[ExportAnswerManifest, ...]

    def body_dict(self) -> dict[str, object]:
        return {
            "exporter_version": self.exporter_version,
            "source_sha256": self.source_sha256,
            "physical_ir_sha256": self.physical_ir_sha256,
            "worksheet_title_sha256": self.worksheet_title_sha256,
            "source_page_count": self.source_page_count,
            "appendix_page_count": self.appendix_page_count,
            "output_page_count": self.output_page_count,
            "output_sha256": self.output_sha256,
            "answers": [answer.to_dict() for answer in self.answers],
        }

    @property
    def manifest_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.body_dict()))

    def to_dict(self) -> dict[str, object]:
        return {**self.body_dict(), "manifest_sha256": self.manifest_sha256}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    pdf_bytes: bytes
    pdf_sha256: str
    manifest: DocumentExportManifest
    placement_plans: tuple[PlacementPlan, ...]
    appendix: AppendixRenderResult


def _answer_order_key(
    document: PhysicalDocumentIR,
    answer: ConfirmedAnswerForExport,
) -> tuple[int, int, str]:
    first = document.block_by_id(answer.prompt_block_ids[0])
    return (first.page_index, first.reading_order, answer.question_id)


def _same_page_shape(source_page: object, output_page: object) -> bool:
    source = source_page
    output = output_page
    return (
        list(source.mediabox) == list(output.mediabox)  # type: ignore[attr-defined]
        and list(source.cropbox) == list(output.cropbox)  # type: ignore[attr-defined]
        and int(source.get("/Rotate", 0)) % 360 == int(output.get("/Rotate", 0)) % 360  # type: ignore[attr-defined]
    )


def _text_runs_present_in_order(expected: str, actual: str) -> bool:
    cursor = 0
    for line in expected.splitlines():
        if not line:
            continue
        found = actual.find(line, cursor)
        if found < 0:
            return False
        cursor = found + len(line)
    return True


def _source_page_objects_preserved(source_page: object, output_page: object) -> bool:
    """Verify source content and interactive objects survive additive assembly."""

    try:
        source_content = source_page.get_contents().get_data().strip()  # type: ignore[attr-defined]
        output_content = output_page.get_contents().get_data()  # type: ignore[attr-defined]
        if source_content and source_content not in output_content:
            return False
        for key in ("/Annots",):
            source_items = source_page.get(key, [])  # type: ignore[attr-defined]
            output_items = output_page.get(key, [])  # type: ignore[attr-defined]
            if len(source_items) != len(output_items):
                return False
        source_resources = source_page.get("/Resources", {})  # type: ignore[attr-defined]
        output_resources = output_page.get("/Resources", {})  # type: ignore[attr-defined]
        if hasattr(source_resources, "get_object"):
            source_resources = source_resources.get_object()
        if hasattr(output_resources, "get_object"):
            output_resources = output_resources.get_object()
        for category in ("/XObject", "/Shading", "/Pattern"):
            source_category = source_resources.get(category, {})
            output_category = output_resources.get(category, {})
            if hasattr(source_category, "get_object"):
                source_category = source_category.get_object()
            if hasattr(output_category, "get_object"):
                output_category = output_category.get_object()
            if any(name not in output_category for name in source_category):
                return False
    except Exception:
        return False
    return True


def _validate_output(
    *,
    source_pdf: bytes,
    output_pdf: bytes,
    document: PhysicalDocumentIR,
    plans: Sequence[PlacementPlan],
    appendix: AppendixRenderResult,
    appendix_entries: Sequence[AppendixEntry],
) -> None:
    expected_pages = len(document.pages) + appendix.page_count
    try:
        with pikepdf.Pdf.open(io.BytesIO(output_pdf), attempt_recovery=False) as checked:
            if checked.is_encrypted or len(checked.pages) != expected_pages:
                raise document_error("invalid_export")
        source_reader = PdfReader(io.BytesIO(source_pdf), strict=True)
        output_reader = PdfReader(io.BytesIO(output_pdf), strict=True)
        if len(output_reader.pages) != expected_pages:
            raise document_error("invalid_export")
        for page_index, source_page in enumerate(source_reader.pages):
            output_page = output_reader.pages[page_index]
            if not _same_page_shape(source_page, output_page):
                raise document_error("invalid_export")
            if not _source_page_objects_preserved(source_page, output_page):
                raise document_error("invalid_export")
            source_text = source_page.extract_text() or ""
            output_text = output_page.extract_text() or ""
            if not _text_runs_present_in_order(source_text, output_text):
                raise document_error("invalid_export")
        output_text_by_page = [(page.extract_text() or "") for page in output_reader.pages]
    except DocumentEngineError:
        raise
    except Exception as error:
        raise document_error("invalid_export") from error

    for plan in plans:
        if plan.outcome == "reject":
            raise document_error("invalid_export")
        if plan.outcome == "inline":
            if plan.region is None or plan.fit is None:
                raise document_error("invalid_export")
            if plan.fit.font_size_mpt < MIN_FONT_SIZE_MPT:
                raise document_error("invalid_export")
            page_text = output_text_by_page[plan.region.page_index]
            if any(line.text and line.text not in page_text for line in plan.fit.lines):
                raise document_error("invalid_export")
    appendix_plans = [plan for plan in plans if plan.outcome == "appendix"]
    if not (len(appendix_plans) == len(appendix_entries) == len(appendix.entries)):
        raise document_error("invalid_export")
    appendix_page_start = len(document.pages)
    for plan, entry, rendered in zip(
        appendix_plans, appendix_entries, appendix.entries, strict=True
    ):
        if (
            entry.question_id != plan.question_id
            or rendered.question_id != plan.question_id
            or not hmac.compare_digest(rendered.exact_answer_sha256, plan.exact_text_sha256)
            or not hmac.compare_digest(
                sha256_hex(entry.exact_answer.encode("utf-8")),
                plan.exact_text_sha256,
            )
            or rendered.page_count < 1
            or not rendered.rendered_answer_lines
        ):
            raise document_error("invalid_export")
        first_page = appendix_page_start + rendered.first_page_offset
        final_page = first_page + rendered.page_count
        if first_page < appendix_page_start or final_page > len(output_text_by_page):
            raise document_error("invalid_export")
        actual_text = "\n".join(output_text_by_page[first_page:final_page])
        if not _text_runs_present_in_order("\n".join(rendered.rendered_answer_lines), actual_text):
            raise document_error("invalid_export")
    source_digest_after = sha256_hex(source_pdf)
    if not hmac.compare_digest(source_digest_after, document.source_sha256):
        raise document_error("stale_source")


def build_export(
    source_pdf: bytes,
    physical_ir: PhysicalDocumentIR,
    worksheet_title: str,
    answers: Sequence[ConfirmedAnswerForExport],
) -> ExportArtifact:
    """Revalidate reviewed answers and build a deterministic derivative PDF."""

    if not answers:
        raise document_error("no_confirmed_answers")
    if not hmac.compare_digest(sha256_hex(source_pdf), physical_ir.source_sha256):
        raise document_error("stale_source")
    current_ir = extract_physical_ir(source_pdf)
    if not hmac.compare_digest(current_ir.ir_sha256, physical_ir.ir_sha256):
        raise document_error("stale_physical_ir")
    question_ids = [answer.question_id for answer in answers]
    if len(question_ids) != len(set(question_ids)):
        raise document_error("invalid_export")
    ordered_answers = sorted(answers, key=lambda answer: _answer_order_key(current_ir, answer))
    plans: list[PlacementPlan] = []
    appendix_entries: list[AppendixEntry] = []
    manifest_answers: list[ExportAnswerManifest] = []
    for answer in ordered_answers:
        evidence = answer.question_evidence()
        exact_question = current_ir.reconstruct_text(evidence.prompt_block_ids)
        plan = resolve_placement(
            current_ir,
            evidence,
            answer.exact_text,
            occupied_plans=plans,
        )
        if plan.outcome == "reject":
            raise document_error("unsafe_question_evidence")
        if not hmac.compare_digest(plan.placement_hash, answer.reviewed_placement_hash):
            forced_appendix = resolve_placement(
                current_ir,
                evidence,
                answer.exact_text,
                occupied_plans=plans,
                force_appendix=True,
            )
            if not hmac.compare_digest(
                forced_appendix.placement_hash, answer.reviewed_placement_hash
            ):
                raise document_error("placement_changed")
            plan = forced_appendix
        prompt = current_ir.block_by_id(evidence.prompt_block_ids[0])
        if plan.outcome == "appendix":
            appendix_entries.append(
                AppendixEntry(
                    question_id=answer.question_id,
                    display_identifier=answer.display_identifier,
                    exact_question=exact_question,
                    source_page_number=prompt.page_index + 1,
                    exact_answer=answer.exact_text,
                    placement_hash=plan.placement_hash,
                )
            )
        plans.append(plan)
        manifest_answers.append(
            ExportAnswerManifest(
                question_id=answer.question_id,
                exact_question_sha256=plan.exact_question_sha256,
                exact_text_sha256=plan.exact_text_sha256,
                placement_hash=plan.placement_hash,
                outcome=plan.outcome,
                source_page_number=prompt.page_index + 1,
                font_size_mpt=plan.fit.font_size_mpt if plan.fit else None,
            )
        )
    appendix = render_appendix(appendix_entries, worksheet_title)
    output_pdf = assemble_derivative(
        source_pdf,
        current_ir,
        [plan for plan in plans if plan.outcome == "inline"],
        appendix,
    )
    _validate_output(
        source_pdf=source_pdf,
        output_pdf=output_pdf,
        document=current_ir,
        plans=plans,
        appendix=appendix,
        appendix_entries=appendix_entries,
    )
    output_sha256 = sha256_hex(output_pdf)
    manifest = DocumentExportManifest(
        exporter_version=EXPORTER_VERSION,
        source_sha256=current_ir.source_sha256,
        physical_ir_sha256=current_ir.ir_sha256,
        worksheet_title_sha256=sha256_hex(worksheet_title.encode("utf-8")),
        source_page_count=len(current_ir.pages),
        appendix_page_count=appendix.page_count,
        output_page_count=len(current_ir.pages) + appendix.page_count,
        output_sha256=output_sha256,
        answers=tuple(manifest_answers),
    )
    return ExportArtifact(
        pdf_bytes=output_pdf,
        pdf_sha256=output_sha256,
        manifest=manifest,
        placement_plans=tuple(plans),
        appendix=appendix,
    )


Published = TypeVar("Published")


@dataclass(frozen=True, slots=True)
class PublicationResult(Generic[Published]):
    reference: Published
    pdf_sha256: str
    manifest_sha256: str


def publish_validated_export(
    artifact: ExportArtifact,
    *,
    publish: Callable[[bytes, bytes], Published],
    cleanup: Callable[[], None],
) -> PublicationResult[Published]:
    """Publish validated immutable bytes and clean partial output on failure."""

    try:
        reference = publish(artifact.pdf_bytes, artifact.manifest.canonical_bytes())
    except Exception as error:
        with suppress(Exception):
            cleanup()
        raise document_error("publish_failed") from error
    return PublicationResult(
        reference=reference,
        pdf_sha256=artifact.pdf_sha256,
        manifest_sha256=artifact.manifest.manifest_sha256,
    )
