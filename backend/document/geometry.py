"""Server-owned placement resolution and deterministic readable fitting."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from backend.document.errors import DocumentEngineError, document_error
from backend.document.fonts import REGULAR_FONT_NAME, ensure_supported_text, register_fonts
from backend.document.models import (
    CanonicalBox,
    PhysicalBlock,
    PhysicalDocumentIR,
    PhysicalPage,
    canonical_json_bytes,
    sha256_hex,
)

PLACEMENT_ALGORITHM_VERSION = "claros-placement-v2.0.1"
DEFAULT_PADDING_MPT = 4_000
DEFAULT_LEADING_RATIO_MILLI = 1_200
MIN_FONT_SIZE_MPT = 10_000
MAX_FONT_SIZE_MPT = 12_000
FONT_STEP_MPT = 500
MIN_REGION_WIDTH_MPT = 100_000
MIN_REGION_HEIGHT_MPT = 24_000
MAX_REGION_DISTANCE_MPT = 280_000

PlacementOutcome = Literal["inline", "appendix", "reject"]
RegionKind = Literal["form_field", "rect", "line_group", "whitespace"]


@dataclass(frozen=True, slots=True)
class QuestionEvidence:
    question_id: str
    display_identifier: str
    prompt_block_ids: tuple[str, ...]
    context_block_ids: tuple[str, ...] = ()
    grounded: bool = True

    def __post_init__(self) -> None:
        if not self.question_id or len(self.question_id) > 96:
            raise document_error("unsafe_question_evidence")
        if not self.display_identifier or len(self.display_identifier) > 128:
            raise document_error("unsafe_question_evidence")
        all_ids = (*self.prompt_block_ids, *self.context_block_ids)
        if (
            not self.prompt_block_ids
            or len(all_ids) != len(set(all_ids))
            or not all(block_id.startswith("blk_") and len(block_id) == 36 for block_id in all_ids)
        ):
            raise document_error("unsafe_question_evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "display_identifier": self.display_identifier,
            "prompt_block_ids": list(self.prompt_block_ids),
            "context_block_ids": list(self.context_block_ids),
            "grounded": self.grounded,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_bytes(cls, payload: bytes) -> QuestionEvidence:
        raw = _strict_json(payload, code="unsafe_question_evidence")
        if not isinstance(raw, dict) or set(raw) != {
            "question_id",
            "display_identifier",
            "prompt_block_ids",
            "context_block_ids",
            "grounded",
        }:
            raise document_error("unsafe_question_evidence")
        prompt_ids = raw["prompt_block_ids"]
        context_ids = raw["context_block_ids"]
        if (
            not isinstance(raw["question_id"], str)
            or not isinstance(raw["display_identifier"], str)
            or not isinstance(prompt_ids, list)
            or not all(isinstance(item, str) for item in prompt_ids)
            or not isinstance(context_ids, list)
            or not all(isinstance(item, str) for item in context_ids)
            or not isinstance(raw["grounded"], bool)
        ):
            raise document_error("unsafe_question_evidence")
        result = cls(
            question_id=raw["question_id"],
            display_identifier=raw["display_identifier"],
            prompt_block_ids=tuple(prompt_ids),
            context_block_ids=tuple(context_ids),
            grounded=raw["grounded"],
        )
        if payload != result.canonical_bytes():
            raise document_error("unsafe_question_evidence")
        return result


@dataclass(frozen=True, slots=True)
class FitLine:
    text: str
    separator_after: str
    x_mpt: int
    baseline_y_mpt: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "separator_after": self.separator_after,
            "x_mpt": self.x_mpt,
            "baseline_y_mpt": self.baseline_y_mpt,
        }


@dataclass(frozen=True, slots=True)
class FitEvidence:
    font_name: str
    font_size_mpt: int
    leading_mpt: int
    padding_mpt: int
    rendered_bounds_mpt: CanonicalBox
    lines: tuple[FitLine, ...]
    scratch_pdf_sha256: str

    def __post_init__(self) -> None:
        if (
            self.font_name != REGULAR_FONT_NAME
            or self.font_size_mpt < MIN_FONT_SIZE_MPT
            or self.font_size_mpt > MAX_FONT_SIZE_MPT
            or self.leading_mpt <= 0
            or self.padding_mpt < 0
            or not self.lines
            or len(self.scratch_pdf_sha256) != 64
        ):
            raise document_error("invalid_physical_evidence")

    def reconstructed_text(self) -> str:
        return "".join(line.text + line.separator_after for line in self.lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "font_name": self.font_name,
            "font_size_mpt": self.font_size_mpt,
            "leading_mpt": self.leading_mpt,
            "padding_mpt": self.padding_mpt,
            "rendered_bounds_mpt": self.rendered_bounds_mpt.to_list(),
            "lines": [line.to_dict() for line in self.lines],
            "scratch_pdf_sha256": self.scratch_pdf_sha256,
        }


@dataclass(frozen=True, slots=True)
class RegionEvidence:
    region_id: str
    kind: RegionKind
    page_index: int
    bbox_mpt: CanonicalBox
    source_block_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.region_id.startswith("region_") or len(self.region_id) != 31:
            raise document_error("invalid_physical_evidence")
        if self.kind not in {"form_field", "rect", "line_group", "whitespace"}:
            raise document_error("invalid_physical_evidence")
        if self.page_index < 0 or len(self.source_block_ids) != len(set(self.source_block_ids)):
            raise document_error("invalid_physical_evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "kind": self.kind,
            "page_index": self.page_index,
            "bbox_mpt": self.bbox_mpt.to_list(),
            "source_block_ids": list(self.source_block_ids),
        }


@dataclass(frozen=True, slots=True)
class PlacementPlan:
    algorithm_version: str
    source_sha256: str
    physical_ir_sha256: str
    question_id: str
    question_evidence_sha256: str
    exact_question_sha256: str
    exact_text_sha256: str
    outcome: PlacementOutcome
    region: RegionEvidence | None
    fit: FitEvidence | None
    appendix_entry_id: str | None
    rejection_code: str | None
    placement_hash: str

    def __post_init__(self) -> None:
        if self.algorithm_version != PLACEMENT_ALGORITHM_VERSION:
            raise document_error("placement_changed")
        if self.outcome not in {"inline", "appendix", "reject"}:
            raise document_error("invalid_physical_evidence")
        if self.outcome == "inline" and (self.region is None or self.fit is None):
            raise document_error("invalid_physical_evidence")
        if self.outcome == "appendix" and not self.appendix_entry_id:
            raise document_error("invalid_physical_evidence")
        if self.outcome == "reject" and not self.rejection_code:
            raise document_error("invalid_physical_evidence")
        if self.outcome != "inline" and (self.region is not None or self.fit is not None):
            raise document_error("invalid_physical_evidence")
        if self.outcome == "inline" and (
            self.appendix_entry_id is not None or self.rejection_code is not None
        ):
            raise document_error("invalid_physical_evidence")
        if self.outcome == "appendix" and self.rejection_code is not None:
            raise document_error("invalid_physical_evidence")
        if self.outcome == "reject" and self.appendix_entry_id is not None:
            raise document_error("invalid_physical_evidence")
        for digest in (
            self.source_sha256,
            self.physical_ir_sha256,
            self.question_evidence_sha256,
            self.exact_question_sha256,
            self.exact_text_sha256,
            self.placement_hash,
        ):
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise document_error("invalid_physical_evidence")

    def body_dict(self) -> dict[str, Any]:
        return {
            "algorithm_version": self.algorithm_version,
            "source_sha256": self.source_sha256,
            "physical_ir_sha256": self.physical_ir_sha256,
            "question_id": self.question_id,
            "question_evidence_sha256": self.question_evidence_sha256,
            "exact_question_sha256": self.exact_question_sha256,
            "exact_text_sha256": self.exact_text_sha256,
            "outcome": self.outcome,
            "region": self.region.to_dict() if self.region else None,
            "fit": self.fit.to_dict() if self.fit else None,
            "appendix_entry_id": self.appendix_entry_id,
            "rejection_code": self.rejection_code,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "placement_hash": self.placement_hash}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


def _strict_json(payload: bytes, *, code: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise document_error(code)
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=lambda _value: (_ for _ in ()).throw(document_error(code)),
        )
    except DocumentEngineError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise document_error(code) from error


def _question_details(
    document: PhysicalDocumentIR,
    evidence: QuestionEvidence,
) -> tuple[PhysicalPage, tuple[PhysicalBlock, ...], str, str]:
    if not evidence.grounded:
        raise document_error("unsafe_question_evidence")
    prompt_blocks = tuple(document.block_by_id(block_id) for block_id in evidence.prompt_block_ids)
    context_blocks = tuple(
        document.block_by_id(block_id) for block_id in evidence.context_block_ids
    )
    if any(block.kind != "text" for block in (*prompt_blocks, *context_blocks)):
        raise document_error("unsafe_question_evidence")
    prompt_orders = [(block.page_index, block.reading_order) for block in prompt_blocks]
    context_orders = [(block.page_index, block.reading_order) for block in context_blocks]
    if prompt_orders != sorted(prompt_orders) or context_orders != sorted(context_orders):
        raise document_error("unsafe_question_evidence")
    if len({block.page_index for block in prompt_blocks}) != 1:
        raise document_error("unsafe_question_evidence")
    exact_question = document.reconstruct_text(evidence.prompt_block_ids)
    if not exact_question.strip():
        raise document_error("unsafe_question_evidence")
    evidence_payload = {
        **evidence.to_dict(),
        "exact_question_sha256": sha256_hex(exact_question.encode("utf-8")),
        "context_sha256": sha256_hex(
            document.reconstruct_text(evidence.context_block_ids).encode("utf-8")
        )
        if evidence.context_block_ids
        else sha256_hex(b""),
    }
    page = document.pages[prompt_blocks[0].page_index]
    return page, prompt_blocks, exact_question, sha256_hex(canonical_json_bytes(evidence_payload))


def _region_id(
    kind: RegionKind,
    page_index: int,
    block_ids: tuple[str, ...],
    box: CanonicalBox,
) -> str:
    seed = canonical_json_bytes(
        {
            "algorithm_version": PLACEMENT_ALGORITHM_VERSION,
            "kind": kind,
            "page_index": page_index,
            "source_block_ids": list(block_ids),
            "bbox_mpt": box.to_list(),
        }
    )
    return "region_" + sha256_hex(seed)[:24]


def _region(
    kind: RegionKind,
    page_index: int,
    block_ids: tuple[str, ...],
    box: CanonicalBox,
) -> RegionEvidence:
    return RegionEvidence(
        region_id=_region_id(kind, page_index, block_ids, box),
        kind=kind,
        page_index=page_index,
        bbox_mpt=box,
        source_block_ids=block_ids,
    )


def _below_prompt(block: PhysicalBlock, prompt_box: CanonicalBox, boundary_mpt: int) -> bool:
    return (
        block.bbox.y0 >= prompt_box.y1 - 1_000
        and block.bbox.y0 <= boundary_mpt
        and block.bbox.y0 - prompt_box.y1 <= MAX_REGION_DISTANCE_MPT
    )


def _next_text_boundary(
    page: PhysicalPage,
    prompt_blocks: tuple[PhysicalBlock, ...],
    prompt_box: CanonicalBox,
) -> int:
    last_order = max(block.reading_order for block in prompt_blocks)
    candidates = [
        block.bbox.y0
        for block in page.blocks
        if block.kind == "text"
        and block.reading_order > last_order
        and block.bbox.y0 > prompt_box.y1 + 2_000
    ]
    return (
        min(candidates) - 4_000
        if candidates
        else min(
            page.height_mpt - 36_000,
            prompt_box.y1 + MAX_REGION_DISTANCE_MPT,
        )
    )


def _collides_with_source(
    page: PhysicalPage,
    region: RegionEvidence,
    prompt_ids: tuple[str, ...],
) -> bool:
    excluded = set((*region.source_block_ids, *prompt_ids))
    for block in page.blocks:
        if block.id in excluded:
            continue
        if block.kind not in {"text", "line", "rect", "shape", "image", "form_field"}:
            continue
        if block.bbox.intersects(region.bbox_mpt, clearance_mpt=1_000):
            return True
    return False


def _form_field_regions(
    page: PhysicalPage,
    prompt_box: CanonicalBox,
    boundary: int,
) -> tuple[RegionEvidence, ...]:
    candidates = [
        block
        for block in page.blocks
        if block.kind == "form_field"
        and block.writable is True
        and block.bbox.width >= MIN_REGION_WIDTH_MPT
        and block.bbox.height >= MIN_REGION_HEIGHT_MPT
        and _below_prompt(block, prompt_box, boundary)
    ]
    return tuple(
        _region("form_field", page.page_index, (block.id,), block.bbox) for block in candidates
    )


def _rect_regions(
    page: PhysicalPage,
    prompt_box: CanonicalBox,
    boundary: int,
) -> tuple[RegionEvidence, ...]:
    candidates = [
        block
        for block in page.blocks
        if block.kind == "rect"
        and block.filled is not True
        and block.bbox.width >= MIN_REGION_WIDTH_MPT
        and block.bbox.height >= MIN_REGION_HEIGHT_MPT
        and _below_prompt(block, prompt_box, boundary)
    ]
    return tuple(_region("rect", page.page_index, (block.id,), block.bbox) for block in candidates)


def _line_regions(
    page: PhysicalPage,
    prompt_box: CanonicalBox,
    boundary: int,
) -> tuple[RegionEvidence, ...]:
    lines = [
        block
        for block in page.blocks
        if block.kind == "line"
        and block.bbox.width >= MIN_REGION_WIDTH_MPT
        and block.bbox.height <= 2_000
        and _below_prompt(block, prompt_box, boundary)
    ]
    lines.sort(key=lambda block: (block.bbox.y0, block.bbox.x0, block.reading_order))
    groups: list[list[PhysicalBlock]] = []
    for line in lines:
        if not groups:
            groups.append([line])
            continue
        previous = groups[-1][-1]
        same_span = (
            abs(line.bbox.x0 - previous.bbox.x0) <= 8_000
            and abs(line.bbox.x1 - previous.bbox.x1) <= 8_000
        )
        vertical_gap = line.bbox.y0 - previous.bbox.y0
        if same_span and 8_000 <= vertical_gap <= 36_000:
            groups[-1].append(line)
        else:
            groups.append([line])

    regions: list[RegionEvidence] = []
    for group in groups:
        first_y = group[0].bbox.y0
        last_y = group[-1].bbox.y1
        box = CanonicalBox(
            x0=max(0, min(line.bbox.x0 for line in group)),
            y0=max(prompt_box.y1 + 2_000, first_y - 18_000),
            x1=min(page.width_mpt, max(line.bbox.x1 for line in group)),
            y1=min(boundary, max(first_y, last_y)),
        )
        if box.width >= MIN_REGION_WIDTH_MPT and box.height >= MIN_REGION_HEIGHT_MPT:
            regions.append(
                _region(
                    "line_group",
                    page.page_index,
                    tuple(line.id for line in group),
                    box,
                )
            )
    return tuple(regions)


def _whitespace_regions(
    page: PhysicalPage,
    prompt_blocks: tuple[PhysicalBlock, ...],
    prompt_box: CanonicalBox,
) -> tuple[RegionEvidence, ...]:
    last_order = max(block.reading_order for block in prompt_blocks)
    following = [
        block
        for block in page.blocks
        if block.kind in {"text", "image"}
        and block.reading_order > last_order
        and block.bbox.y0 > prompt_box.y1 + 24_000
    ]
    if not following:
        return ()
    next_block = min(following, key=lambda block: (block.bbox.y0, block.bbox.x0))
    box = CanonicalBox(
        x0=max(36_000, prompt_box.x0),
        y0=prompt_box.y1 + 8_000,
        x1=page.width_mpt - 36_000,
        y1=next_block.bbox.y0 - 8_000,
    )
    if box.width < MIN_REGION_WIDTH_MPT or box.height < MIN_REGION_HEIGHT_MPT:
        return ()
    return (_region("whitespace", page.page_index, (), box),)


def _wrap_paragraph(
    text: str,
    max_width_mpt: int,
    measure: Callable[[str], int],
) -> list[tuple[str, str]] | None:
    if measure(text) <= max_width_mpt:
        return [(text, "")]
    result: list[tuple[str, str]] = []
    remaining = text
    while remaining and measure(remaining) > max_width_mpt:
        selected: tuple[int, int] | None = None
        for match in re.finditer(r"[^\S\r\n]+", remaining):
            if match.start() == 0:
                continue
            if measure(remaining[: match.start()]) <= max_width_mpt:
                selected = (match.start(), match.end())
            else:
                break
        if selected is None:
            return None
        start, end = selected
        result.append((remaining[:start], remaining[start:end]))
        remaining = remaining[end:]
    result.append((remaining, ""))
    return result


def _wrap_exact_text(
    text: str,
    max_width_mpt: int,
    font_size_mpt: int,
) -> tuple[FitLine, ...] | None:
    font_size = font_size_mpt / 1000

    def measure(value: str) -> int:
        return round(pdfmetrics.stringWidth(value, REGULAR_FONT_NAME, font_size) * 1000)

    parts = re.split(r"(\r\n|\r|\n)", text)
    lines: list[tuple[str, str]] = []
    for index in range(0, len(parts), 2):
        paragraph = parts[index]
        newline = parts[index + 1] if index + 1 < len(parts) else ""
        wrapped = _wrap_paragraph(paragraph, max_width_mpt, measure)
        if wrapped is None:
            return None
        if not wrapped:
            wrapped = [("", "")]
        if newline:
            last_text, last_separator = wrapped[-1]
            wrapped[-1] = (last_text, last_separator + newline)
        lines.extend(wrapped)
    return tuple(
        FitLine(text=line, separator_after=separator, x_mpt=0, baseline_y_mpt=0)
        for line, separator in lines
    )


def _scratch_render(
    lines: tuple[FitLine, ...],
    *,
    width_mpt: int,
    height_mpt: int,
    font_size_mpt: int,
    origin_x_mpt: int,
    origin_y_mpt: int,
) -> str:
    import io

    from pypdf import PdfReader

    buffer = io.BytesIO()
    scratch = canvas.Canvas(
        buffer,
        pagesize=(width_mpt / 1000, height_mpt / 1000),
        invariant=1,
        pageCompression=1,
    )
    scratch.setFont(REGULAR_FONT_NAME, font_size_mpt / 1000)
    for line in lines:
        x_points = (line.x_mpt - origin_x_mpt) / 1000
        y_points = (height_mpt - (line.baseline_y_mpt - origin_y_mpt)) / 1000
        scratch.drawString(x_points, y_points, line.text)
    scratch.save()
    payload = buffer.getvalue()
    if not payload.startswith(b"%PDF-"):
        raise document_error("invalid_physical_evidence")
    try:
        extracted = PdfReader(io.BytesIO(payload), strict=True).pages[0].extract_text() or ""
    except Exception as error:
        raise document_error("invalid_physical_evidence") from error
    if any(line.text and line.text not in extracted for line in lines):
        raise document_error("invalid_physical_evidence")
    return sha256_hex(payload)


def fit_text(region: RegionEvidence, exact_text: str) -> FitEvidence | None:
    """Prove a readable fit on a scratch PDF before any source page is touched."""

    ensure_supported_text(exact_text)
    register_fonts()
    available_width = region.bbox_mpt.width - 2 * DEFAULT_PADDING_MPT
    available_height = region.bbox_mpt.height - 2 * DEFAULT_PADDING_MPT
    if available_width <= 0 or available_height <= 0:
        return None
    for font_size_mpt in range(MAX_FONT_SIZE_MPT, MIN_FONT_SIZE_MPT - 1, -FONT_STEP_MPT):
        leading_mpt = font_size_mpt * DEFAULT_LEADING_RATIO_MILLI // 1000
        provisional = _wrap_exact_text(exact_text, available_width, font_size_mpt)
        if provisional is None or len(provisional) * leading_mpt > available_height:
            continue
        lines = tuple(
            FitLine(
                text=line.text,
                separator_after=line.separator_after,
                x_mpt=region.bbox_mpt.x0 + DEFAULT_PADDING_MPT,
                baseline_y_mpt=(
                    region.bbox_mpt.y0 + DEFAULT_PADDING_MPT + font_size_mpt + index * leading_mpt
                ),
            )
            for index, line in enumerate(provisional)
        )
        max_width = max(
            round(pdfmetrics.stringWidth(line.text, REGULAR_FONT_NAME, font_size_mpt / 1000) * 1000)
            for line in lines
        )
        rendered = CanonicalBox(
            x0=region.bbox_mpt.x0 + DEFAULT_PADDING_MPT,
            y0=region.bbox_mpt.y0 + DEFAULT_PADDING_MPT,
            x1=region.bbox_mpt.x0 + DEFAULT_PADDING_MPT + max(1, max_width),
            y1=region.bbox_mpt.y0 + DEFAULT_PADDING_MPT + len(lines) * leading_mpt,
        )
        if rendered.x1 > region.bbox_mpt.x1 - DEFAULT_PADDING_MPT:
            continue
        if rendered.y1 > region.bbox_mpt.y1 - DEFAULT_PADDING_MPT:
            continue
        scratch_hash = _scratch_render(
            lines,
            width_mpt=max(1, region.bbox_mpt.width),
            height_mpt=max(1, region.bbox_mpt.height),
            font_size_mpt=font_size_mpt,
            origin_x_mpt=region.bbox_mpt.x0,
            origin_y_mpt=region.bbox_mpt.y0,
        )
        evidence = FitEvidence(
            font_name=REGULAR_FONT_NAME,
            font_size_mpt=font_size_mpt,
            leading_mpt=leading_mpt,
            padding_mpt=DEFAULT_PADDING_MPT,
            rendered_bounds_mpt=rendered,
            lines=lines,
            scratch_pdf_sha256=scratch_hash,
        )
        if evidence.reconstructed_text() != exact_text:
            raise document_error("invalid_physical_evidence")
        return evidence
    return None


def _make_plan(
    *,
    document: PhysicalDocumentIR,
    evidence: QuestionEvidence,
    evidence_hash: str,
    exact_question: str,
    exact_text: str,
    outcome: PlacementOutcome,
    region: RegionEvidence | None = None,
    fit: FitEvidence | None = None,
    rejection_code: str | None = None,
) -> PlacementPlan:
    appendix_entry_id = None
    if outcome == "appendix":
        appendix_entry_id = (
            "appendix_"
            + sha256_hex(
                canonical_json_bytes(
                    {
                        "question_id": evidence.question_id,
                        "question_evidence_sha256": evidence_hash,
                        "exact_text_sha256": sha256_hex(exact_text.encode("utf-8")),
                    }
                )
            )[:24]
        )
    body = {
        "algorithm_version": PLACEMENT_ALGORITHM_VERSION,
        "source_sha256": document.source_sha256,
        "physical_ir_sha256": document.ir_sha256,
        "question_id": evidence.question_id,
        "question_evidence_sha256": evidence_hash,
        "exact_question_sha256": sha256_hex(exact_question.encode("utf-8")),
        "exact_text_sha256": sha256_hex(exact_text.encode("utf-8")),
        "outcome": outcome,
        "region": region.to_dict() if region else None,
        "fit": fit.to_dict() if fit else None,
        "appendix_entry_id": appendix_entry_id,
        "rejection_code": rejection_code,
    }
    return PlacementPlan(
        algorithm_version=PLACEMENT_ALGORITHM_VERSION,
        source_sha256=document.source_sha256,
        physical_ir_sha256=document.ir_sha256,
        question_id=evidence.question_id,
        question_evidence_sha256=evidence_hash,
        exact_question_sha256=body["exact_question_sha256"],
        exact_text_sha256=body["exact_text_sha256"],
        outcome=outcome,
        region=region,
        fit=fit,
        appendix_entry_id=appendix_entry_id,
        rejection_code=rejection_code,
        placement_hash=sha256_hex(canonical_json_bytes(body)),
    )


def _appendix_plan(
    document: PhysicalDocumentIR,
    evidence: QuestionEvidence,
    evidence_hash: str,
    exact_question: str,
    exact_text: str,
) -> PlacementPlan:
    return _make_plan(
        document=document,
        evidence=evidence,
        evidence_hash=evidence_hash,
        exact_question=exact_question,
        exact_text=exact_text,
        outcome="appendix",
    )


def resolve_placement(
    document: PhysicalDocumentIR,
    evidence: QuestionEvidence,
    exact_text: str,
    *,
    occupied_plans: Sequence[PlacementPlan] = (),
    force_appendix: bool = False,
) -> PlacementPlan:
    """Derive a placement solely from stored physical evidence and exact text."""

    try:
        page, prompt_blocks, exact_question, evidence_hash = _question_details(document, evidence)
    except DocumentEngineError as error:
        if error.code != "unsafe_question_evidence":
            raise
        fallback_hash = sha256_hex(evidence.canonical_bytes())
        return _make_plan(
            document=document,
            evidence=evidence,
            evidence_hash=fallback_hash,
            exact_question="",
            exact_text=exact_text,
            outcome="reject",
            rejection_code="unsafe_question_evidence",
        )
    ensure_supported_text(exact_text)
    if not exact_text or not exact_text.strip():
        raise document_error("invalid_physical_evidence")
    if force_appendix or not page.has_identity_inline_transform:
        return _appendix_plan(document, evidence, evidence_hash, exact_question, exact_text)

    prompt_box = CanonicalBox.union(tuple(block.bbox for block in prompt_blocks))
    boundary = _next_text_boundary(page, prompt_blocks, prompt_box)
    candidate_groups: tuple[tuple[RegionEvidence, ...], ...] = (
        _form_field_regions(page, prompt_box, boundary),
        _rect_regions(page, prompt_box, boundary),
        _line_regions(page, prompt_box, boundary),
        _whitespace_regions(page, prompt_blocks, prompt_box),
    )
    occupied_boxes = tuple(
        plan.region.bbox_mpt
        for plan in occupied_plans
        if plan.outcome == "inline" and plan.region and plan.region.page_index == page.page_index
    )
    for candidates in candidate_groups:
        if not candidates:
            continue
        if len(candidates) != 1:
            return _appendix_plan(document, evidence, evidence_hash, exact_question, exact_text)
        candidate = candidates[0]
        if _collides_with_source(page, candidate, evidence.prompt_block_ids) or any(
            candidate.bbox_mpt.intersects(box, clearance_mpt=1_000) for box in occupied_boxes
        ):
            continue
        fit = fit_text(candidate, exact_text)
        if fit is None:
            continue
        return _make_plan(
            document=document,
            evidence=evidence,
            evidence_hash=evidence_hash,
            exact_question=exact_question,
            exact_text=exact_text,
            outcome="inline",
            region=candidate,
            fit=fit,
        )
    return _appendix_plan(document, evidence, evidence_hash, exact_question, exact_text)


def validate_placement_plan(
    document: PhysicalDocumentIR,
    evidence: QuestionEvidence,
    exact_text: str,
    reviewed_plan: PlacementPlan,
    *,
    occupied_plans: Sequence[PlacementPlan] = (),
) -> PlacementPlan:
    if reviewed_plan.source_sha256 != document.source_sha256:
        raise document_error("stale_source")
    if reviewed_plan.physical_ir_sha256 != document.ir_sha256:
        raise document_error("stale_physical_ir")
    current = resolve_placement(
        document,
        evidence,
        exact_text,
        occupied_plans=occupied_plans,
    )
    if current.placement_hash != reviewed_plan.placement_hash:
        raise document_error("placement_changed")
    return current


def canonical_box_to_pdf_points(
    page: PhysicalPage,
    box: CanonicalBox,
) -> tuple[float, float, float, float]:
    if not box.within(page.width_mpt, page.height_mpt):
        raise document_error("invalid_physical_evidence")
    corners = (
        page.canonical_to_pdf_mpt.apply(box.x0, box.y0),
        page.canonical_to_pdf_mpt.apply(box.x0, box.y1),
        page.canonical_to_pdf_mpt.apply(box.x1, box.y0),
        page.canonical_to_pdf_mpt.apply(box.x1, box.y1),
    )
    x_values = [point[0] for point in corners]
    y_values = [point[1] for point in corners]
    return (
        min(x_values) / 1000,
        min(y_values) / 1000,
        max(x_values) / 1000,
        max(y_values) / 1000,
    )


def _parse_region(value: object) -> RegionEvidence | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "region_id",
        "kind",
        "page_index",
        "bbox_mpt",
        "source_block_ids",
    }:
        raise document_error("placement_changed")
    bbox = value["bbox_mpt"]
    block_ids = value["source_block_ids"]
    if (
        not isinstance(value["region_id"], str)
        or not isinstance(value["kind"], str)
        or not isinstance(value["page_index"], int)
        or isinstance(value["page_index"], bool)
        or not isinstance(bbox, list)
        or len(bbox) != 4
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in bbox)
        or not isinstance(block_ids, list)
        or not all(isinstance(item, str) for item in block_ids)
    ):
        raise document_error("placement_changed")
    return RegionEvidence(
        region_id=value["region_id"],
        kind=cast(RegionKind, value["kind"]),
        page_index=value["page_index"],
        bbox_mpt=CanonicalBox(*bbox),
        source_block_ids=tuple(block_ids),
    )


def _parse_fit(value: object) -> FitEvidence | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "font_name",
        "font_size_mpt",
        "leading_mpt",
        "padding_mpt",
        "rendered_bounds_mpt",
        "lines",
        "scratch_pdf_sha256",
    }:
        raise document_error("placement_changed")
    bounds = value["rendered_bounds_mpt"]
    raw_lines = value["lines"]
    integer_fields = ("font_size_mpt", "leading_mpt", "padding_mpt")
    if (
        not isinstance(value["font_name"], str)
        or not isinstance(value["scratch_pdf_sha256"], str)
        or any(
            not isinstance(value[field], int) or isinstance(value[field], bool)
            for field in integer_fields
        )
        or not isinstance(bounds, list)
        or len(bounds) != 4
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in bounds)
        or not isinstance(raw_lines, list)
    ):
        raise document_error("placement_changed")
    lines: list[FitLine] = []
    for raw in raw_lines:
        if not isinstance(raw, dict) or set(raw) != {
            "text",
            "separator_after",
            "x_mpt",
            "baseline_y_mpt",
        }:
            raise document_error("placement_changed")
        if (
            not isinstance(raw["text"], str)
            or not isinstance(raw["separator_after"], str)
            or not isinstance(raw["x_mpt"], int)
            or isinstance(raw["x_mpt"], bool)
            or not isinstance(raw["baseline_y_mpt"], int)
            or isinstance(raw["baseline_y_mpt"], bool)
        ):
            raise document_error("placement_changed")
        lines.append(
            FitLine(
                text=raw["text"],
                separator_after=raw["separator_after"],
                x_mpt=raw["x_mpt"],
                baseline_y_mpt=raw["baseline_y_mpt"],
            )
        )
    return FitEvidence(
        font_name=value["font_name"],
        font_size_mpt=value["font_size_mpt"],
        leading_mpt=value["leading_mpt"],
        padding_mpt=value["padding_mpt"],
        rendered_bounds_mpt=CanonicalBox(*bounds),
        lines=tuple(lines),
        scratch_pdf_sha256=value["scratch_pdf_sha256"],
    )


def parse_placement_plan(payload: bytes) -> PlacementPlan:
    raw = _strict_json(payload, code="placement_changed")
    expected = {
        "algorithm_version",
        "source_sha256",
        "physical_ir_sha256",
        "question_id",
        "question_evidence_sha256",
        "exact_question_sha256",
        "exact_text_sha256",
        "outcome",
        "region",
        "fit",
        "appendix_entry_id",
        "rejection_code",
        "placement_hash",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise document_error("placement_changed")
    string_fields = (
        "algorithm_version",
        "source_sha256",
        "physical_ir_sha256",
        "question_id",
        "question_evidence_sha256",
        "exact_question_sha256",
        "exact_text_sha256",
        "outcome",
        "placement_hash",
    )
    if any(not isinstance(raw[field], str) for field in string_fields):
        raise document_error("placement_changed")
    for field in ("appendix_entry_id", "rejection_code"):
        if raw[field] is not None and not isinstance(raw[field], str):
            raise document_error("placement_changed")
    try:
        result = PlacementPlan(
            algorithm_version=raw["algorithm_version"],
            source_sha256=raw["source_sha256"],
            physical_ir_sha256=raw["physical_ir_sha256"],
            question_id=raw["question_id"],
            question_evidence_sha256=raw["question_evidence_sha256"],
            exact_question_sha256=raw["exact_question_sha256"],
            exact_text_sha256=raw["exact_text_sha256"],
            outcome=cast(PlacementOutcome, raw["outcome"]),
            region=_parse_region(raw["region"]),
            fit=_parse_fit(raw["fit"]),
            appendix_entry_id=cast(str | None, raw["appendix_entry_id"]),
            rejection_code=cast(str | None, raw["rejection_code"]),
            placement_hash=raw["placement_hash"],
        )
    except DocumentEngineError as error:
        # A plan is persisted review evidence.  Any structurally impossible
        # value at this boundary is a changed plan, not new source geometry.
        raise document_error("placement_changed") from error
    expected_hash = sha256_hex(canonical_json_bytes(result.body_dict()))
    if result.placement_hash != expected_hash or payload != result.canonical_bytes():
        raise document_error("placement_changed")
    return result
