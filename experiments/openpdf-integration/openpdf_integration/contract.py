"""Strict, renderer-neutral contract crossing the experimental worker boundary."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
OpaqueId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{7,95}$")]
SafeLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceBinding(StrictModel):
    source_id: OpaqueId
    sha256: Digest
    size_bytes: int = Field(ge=1)
    page_count: int = Field(ge=1)
    physical_ir_sha256: Digest
    evidence_version: SafeLabel


class ResourceLimits(StrictModel):
    max_input_bytes: int = Field(ge=1)
    max_output_bytes: int = Field(ge=1)
    max_pages: int = Field(ge=1, le=10_000)


class PageGeometry(StrictModel):
    page_number: int = Field(ge=1)
    media_box_mpt: tuple[int, int, int, int]
    crop_box_mpt: tuple[int, int, int, int]
    rotation: Literal[0, 90, 180, 270]
    user_unit: Annotated[str, StringConstraints(pattern=r"^[0-9]+(?:\.[0-9]+)?$")]
    canonical_to_pdf_mpt: tuple[int, int, int, int, int, int]

    @model_validator(mode="after")
    def valid_boxes(self) -> PageGeometry:
        for box in (self.media_box_mpt, self.crop_box_mpt):
            if box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError("page boxes must have positive area")
        if int(self.user_unit.split(".", 1)[0]) <= 0 and float(self.user_unit) <= 0:
            raise ValueError("user_unit must be positive")
        a, b, c, d, _e, _f = self.canonical_to_pdf_mpt
        if a * d - b * c not in {-1, 1}:
            raise ValueError("page transform must be a quarter-turn isometry")
        return self


class GeneratedLine(StrictModel):
    text: Annotated[str, StringConstraints(min_length=1, max_length=16_384)]
    separator_after: Literal["", " ", "\n"]
    x_mpt: int = Field(ge=0)
    baseline_y_mpt: int = Field(ge=0)
    font_size_mpt: int = Field(ge=1_000, le=72_000)


class ContinuationInstruction(StrictModel):
    worksheet_title: SafeLabel
    source_question: Annotated[str, StringConstraints(min_length=1, max_length=32_768)]
    source_page_number: int = Field(ge=1)
    paragraphs: tuple[Annotated[str, StringConstraints(min_length=1, max_length=262_144)], ...]

    @model_validator(mode="after")
    def has_paragraphs(self) -> ContinuationInstruction:
        if not self.paragraphs:
            raise ValueError("continuation requires at least one paragraph")
        return self


class RenderAnswer(StrictModel):
    question_id: OpaqueId
    display_identifier: SafeLabel
    committed_text: Annotated[str, StringConstraints(min_length=1, max_length=1_048_576)]
    committed_text_sha256: Digest
    placement_hash: Digest
    placement_classification: Literal["inline", "appendix"]
    page_number: int = Field(ge=1)
    lines: tuple[GeneratedLine, ...] = ()
    continuation: ContinuationInstruction | None = None

    @model_validator(mode="after")
    def consistent_placement(self) -> RenderAnswer:
        import hashlib

        actual = hashlib.sha256(self.committed_text.encode("utf-8")).hexdigest()
        if actual != self.committed_text_sha256:
            raise ValueError("committed text hash mismatch")
        if self.placement_classification == "inline":
            if not self.lines or self.continuation is not None:
                raise ValueError("inline answer requires lines only")
            reconstructed = "".join(line.text + line.separator_after for line in self.lines)
            if reconstructed != self.committed_text:
                raise ValueError("inline lines do not reconstruct committed text")
        elif self.lines or self.continuation is None:
            raise ValueError("appendix answer requires continuation instructions only")
        if (
            self.continuation is not None
            and "\n\n".join(self.continuation.paragraphs) != self.committed_text
        ):
            raise ValueError("continuation paragraphs do not reconstruct committed text")
        return self


class PdfRenderJob(StrictModel):
    schema_version: Literal[1]
    operation: Literal["render"]
    job_id: OpaqueId
    source: SourceBinding
    limits: ResourceLimits
    font_id: Literal["noto-sans-regular-v1"]
    font_sha256: Digest
    pages: tuple[PageGeometry, ...]
    answers: tuple[RenderAnswer, ...]

    @model_validator(mode="after")
    def internally_consistent(self) -> PdfRenderJob:
        if not self.answers:
            raise ValueError("render job requires committed answers")
        if len(self.pages) != self.source.page_count:
            raise ValueError("page geometry count differs from source binding")
        if [page.page_number for page in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("page geometry must be sequential")
        if self.source.size_bytes > self.limits.max_input_bytes:
            raise ValueError("input exceeds contract limit")
        if self.source.page_count > self.limits.max_pages:
            raise ValueError("page count exceeds contract limit")
        question_ids = [answer.question_id for answer in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("question ids must be unique")
        if any(answer.page_number > self.source.page_count for answer in self.answers):
            raise ValueError("answer page is outside source")
        return self

    def canonical_bytes(self) -> bytes:
        return (
            json.dumps(
                self.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )

    @classmethod
    def from_bytes(cls, payload: bytes) -> PdfRenderJob:
        parsed = cls.model_validate_json(payload, strict=True)
        if parsed.canonical_bytes() != payload:
            raise ValueError("job contract is not canonical")
        return parsed


class WorkerSuccess(StrictModel):
    schema_version: Literal[1]
    status: Literal["ok"]
    job_id: OpaqueId
    source_sha256: Digest
    output_sha256: Digest
    output_bytes: int = Field(ge=1)
    source_pages: int = Field(ge=1)
    continuation_pages: int = Field(ge=0)
    output_pages: int = Field(ge=1)
    reader_rebuilt: Literal[False]
    incremental: Literal[True]
    render_millis: int = Field(ge=0)


class ValidatorSuccess(StrictModel):
    schema_version: Literal[1]
    status: Literal["ok"]
    job_id: OpaqueId
    validator: Literal["pdfbox", "pdfjs"]
    page_count: int = Field(ge=1)
    generated_text_exact: Literal[True]
    placement_exact: bool | None = None
    source_preserved: bool | None = None
    rendered_pages: int | None = Field(default=None, ge=1)
