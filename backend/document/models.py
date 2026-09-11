"""Canonical immutable models for physical PDF evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Self

from backend.document.errors import document_error

PARSER_VERSION = "claros-physical-ir-v2.0.1"
IR_SCHEMA_VERSION = 1

BlockKind = Literal["text", "line", "rect", "shape", "form_field", "image"]
JoinAfter = Literal["none", "space", "newline"]


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class PdfBoxMpt:
    """An absolute PDF box in physical milli-points."""

    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        if not all(_is_int(value) for value in (self.x0, self.y0, self.x1, self.y1)):
            raise document_error("invalid_physical_evidence")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise document_error("invalid_physical_evidence")

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def to_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass(frozen=True, slots=True)
class CanonicalBox:
    """Crop-relative, top-left geometry in integer milli-points."""

    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        if not all(_is_int(value) for value in (self.x0, self.y0, self.x1, self.y1)):
            raise document_error("invalid_physical_evidence")
        if min(self.x0, self.y0) < 0 or self.x1 < self.x0 or self.y1 < self.y0:
            raise document_error("invalid_physical_evidence")
        if self.x0 == self.x1 and self.y0 == self.y1:
            raise document_error("invalid_physical_evidence")

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]

    def within(self, width_mpt: int, height_mpt: int) -> bool:
        return self.x1 <= width_mpt and self.y1 <= height_mpt

    def intersects(self, other: CanonicalBox, *, clearance_mpt: int = 0) -> bool:
        return not (
            self.x1 + clearance_mpt <= other.x0
            or other.x1 + clearance_mpt <= self.x0
            or self.y1 + clearance_mpt <= other.y0
            or other.y1 + clearance_mpt <= self.y0
        )

    @classmethod
    def union(cls, boxes: tuple[CanonicalBox, ...]) -> Self:
        if not boxes:
            raise document_error("invalid_physical_evidence")
        return cls(
            x0=min(box.x0 for box in boxes),
            y0=min(box.y0 for box in boxes),
            x1=max(box.x1 for box in boxes),
            y1=max(box.y1 for box in boxes),
        )


@dataclass(frozen=True, slots=True)
class AffineTransformMpt:
    """Maps canonical milli-points to absolute PDF physical milli-points."""

    a: int
    b: int
    c: int
    d: int
    e: int
    f: int

    def __post_init__(self) -> None:
        if not all(_is_int(value) for value in self.to_list()):
            raise document_error("invalid_physical_evidence")
        if self.a * self.d - self.b * self.c not in {-1, 1}:
            raise document_error("invalid_physical_evidence")

    def to_list(self) -> list[int]:
        return [self.a, self.b, self.c, self.d, self.e, self.f]

    def apply(self, x_mpt: int, y_mpt: int) -> tuple[int, int]:
        return (
            self.a * x_mpt + self.c * y_mpt + self.e,
            self.b * x_mpt + self.d * y_mpt + self.f,
        )

    def inverse_apply(self, x_mpt: int, y_mpt: int) -> tuple[int, int]:
        determinant = self.a * self.d - self.b * self.c
        translated_x = x_mpt - self.e
        translated_y = y_mpt - self.f
        return (
            (self.d * translated_x - self.c * translated_y) // determinant,
            (-self.b * translated_x + self.a * translated_y) // determinant,
        )


@dataclass(frozen=True, slots=True)
class PhysicalBlock:
    id: str
    kind: BlockKind
    page_index: int
    reading_order: int
    bbox: CanonicalBox
    text: str | None = None
    join_after: JoinAfter = "none"
    field_name: str | None = None
    writable: bool | None = None
    multiline: bool | None = None
    max_length: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    stroke_width_mpt: int | None = None
    filled: bool | None = None
    stroked: bool | None = None
    ambiguity_flags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.id.startswith("blk_") or len(self.id) != 36:
            raise document_error("invalid_physical_evidence")
        if self.kind not in {"text", "line", "rect", "shape", "form_field", "image"}:
            raise document_error("invalid_physical_evidence")
        if self.page_index < 0 or self.reading_order < 0:
            raise document_error("invalid_physical_evidence")
        if self.kind == "text":
            if self.text is None or self.join_after not in {"none", "space", "newline"}:
                raise document_error("invalid_physical_evidence")
        elif self.text is not None or self.join_after != "none":
            raise document_error("invalid_physical_evidence")
        if tuple(sorted(set(self.ambiguity_flags))) != self.ambiguity_flags:
            raise document_error("invalid_physical_evidence")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "page_index": self.page_index,
            "reading_order": self.reading_order,
            "bbox_mpt": self.bbox.to_list(),
            "join_after": self.join_after,
            "ambiguity_flags": list(self.ambiguity_flags),
        }
        optional = {
            "text": self.text,
            "field_name": self.field_name,
            "writable": self.writable,
            "multiline": self.multiline,
            "max_length": self.max_length,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "stroke_width_mpt": self.stroke_width_mpt,
            "filled": self.filled,
            "stroked": self.stroked,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


@dataclass(frozen=True, slots=True)
class PhysicalPage:
    page_index: int
    media_box_mpt: PdfBoxMpt
    crop_box_mpt: PdfBoxMpt
    width_mpt: int
    height_mpt: int
    rotation: int
    user_unit: str
    canonical_to_pdf_mpt: AffineTransformMpt
    blocks: tuple[PhysicalBlock, ...]
    ambiguity_flags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.page_index < 0 or self.width_mpt <= 0 or self.height_mpt <= 0:
            raise document_error("invalid_physical_evidence")
        if self.rotation not in {0, 90, 180, 270}:
            raise document_error("invalid_physical_evidence")
        if not self.user_unit or tuple(sorted(set(self.ambiguity_flags))) != self.ambiguity_flags:
            raise document_error("invalid_physical_evidence")
        orders = [block.reading_order for block in self.blocks]
        ids = [block.id for block in self.blocks]
        if orders != list(range(len(self.blocks))) or len(ids) != len(set(ids)):
            raise document_error("invalid_physical_evidence")
        if any(
            block.page_index != self.page_index
            or not block.bbox.within(self.width_mpt, self.height_mpt)
            for block in self.blocks
        ):
            raise document_error("invalid_physical_evidence")

    @property
    def has_identity_inline_transform(self) -> bool:
        return (
            self.rotation == 0
            and self.user_unit == "1"
            and self.media_box_mpt == self.crop_box_mpt
            and self.media_box_mpt.x0 == 0
            and self.media_box_mpt.y0 == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "page_number": self.page_index + 1,
            "media_box_mpt": self.media_box_mpt.to_list(),
            "crop_box_mpt": self.crop_box_mpt.to_list(),
            "width_mpt": self.width_mpt,
            "height_mpt": self.height_mpt,
            "rotation": self.rotation,
            "user_unit": self.user_unit,
            "canonical_to_pdf_mpt": self.canonical_to_pdf_mpt.to_list(),
            "ambiguity_flags": list(self.ambiguity_flags),
            "blocks": [block.to_dict() for block in self.blocks],
        }


@dataclass(frozen=True, slots=True)
class PhysicalDocumentIR:
    document_id: str
    source_sha256: str
    normalization_sha256: str
    source_size_bytes: int
    pages: tuple[PhysicalPage, ...]
    parser_version: str = PARSER_VERSION
    schema_version: int = IR_SCHEMA_VERSION
    ambiguity_flags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.document_id.startswith("doc_") or len(self.document_id) != 28:
            raise document_error("invalid_physical_evidence")
        for digest in (self.source_sha256, self.normalization_sha256):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise document_error("invalid_physical_evidence")
        if self.source_size_bytes <= 0 or not self.pages:
            raise document_error("invalid_physical_evidence")
        if [page.page_index for page in self.pages] != list(range(len(self.pages))):
            raise document_error("invalid_physical_evidence")
        block_ids = [block.id for page in self.pages for block in page.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise document_error("invalid_physical_evidence")
        if tuple(sorted(set(self.ambiguity_flags))) != self.ambiguity_flags:
            raise document_error("invalid_physical_evidence")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "document_id": self.document_id,
            "source_sha256": self.source_sha256,
            "normalization_sha256": self.normalization_sha256,
            "source_size_bytes": self.source_size_bytes,
            "ambiguity_flags": list(self.ambiguity_flags),
            "pages": [page.to_dict() for page in self.pages],
        }

    @property
    def ir_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.body_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "ir_sha256": self.ir_sha256}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    def block_by_id(self, block_id: str) -> PhysicalBlock:
        for page in self.pages:
            for block in page.blocks:
                if block.id == block_id:
                    return block
        raise document_error("unsafe_question_evidence")

    def reconstruct_text(self, block_ids: tuple[str, ...]) -> str:
        if not block_ids or len(block_ids) != len(set(block_ids)):
            raise document_error("unsafe_question_evidence")
        blocks = tuple(self.block_by_id(block_id) for block_id in block_ids)
        if any(block.kind != "text" for block in blocks):
            raise document_error("unsafe_question_evidence")
        order = [(block.page_index, block.reading_order) for block in blocks]
        if order != sorted(order):
            raise document_error("unsafe_question_evidence")
        result: list[str] = []
        for index, block in enumerate(blocks):
            result.append(block.text or "")
            if index == len(blocks) - 1:
                continue
            if block.join_after == "space":
                result.append(" ")
            elif block.join_after == "newline":
                result.append("\n")
        return "".join(result)
