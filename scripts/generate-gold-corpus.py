"""Generate and verify the license-safe Claros V2 gold PDF corpus."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "backend" / "tests" / "corpus"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
GENERATOR_VERSION = "claros-gold-corpus-v1"
NOTO_REGULAR = ROOT / "assets" / "fonts" / "noto-sans" / "NotoSans-Regular.ttf"


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    filename: str
    title: str
    pages: tuple[tuple[str, ...], ...]
    expected: dict[str, object]
    style: Literal["lines", "boxes", "dense", "plain", "scan"] = "lines"
    unicode_font: bool = False
    rotate: int = 0
    crop: bool = False


FIXTURES = (
    Fixture(
        fixture_id="biology-polished",
        filename="01-biology-polished.pdf",
        title="Cell Energy Review",
        pages=(
            (
                "1. What organelle releases usable energy from food?",
                "2. Why do plant cells need chloroplasts?",
            ),
        ),
        expected={
            "outcome": "accept",
            "question_text": [
                "1. What organelle releases usable energy from food?",
                "2. Why do plant cells need chloroplasts?",
            ],
            "placement": "inline",
        },
    ),
    Fixture(
        fixture_id="middle-school-science",
        filename="02-middle-school-science.pdf",
        title="Forces and Motion",
        pages=(
            (
                "1. What happens to speed when a net force increases?",
                "2. Give one example of friction helping you.",
            ),
        ),
        expected={
            "outcome": "accept",
            "question_text": [
                "1. What happens to speed when a net force increases?",
                "2. Give one example of friction helping you.",
            ],
            "placement": "inline",
        },
    ),
    Fixture(
        fixture_id="non-science-short-answer",
        filename="03-non-science-short-answer.pdf",
        title="Civic Participation",
        pages=(
            (
                "1. Why is voting one way citizens participate?",
                "2. Name one responsibility of a local government.",
            ),
        ),
        expected={
            "outcome": "accept",
            "question_text": [
                "1. Why is voting one way citizens participate?",
                "2. Name one responsibility of a local government.",
            ],
            "placement": "inline",
        },
    ),
    Fixture(
        fixture_id="blank-answer-lines",
        filename="04-blank-answer-lines.pdf",
        title="Weather Check",
        pages=(("1. How does warm air usually move?",),),
        expected={
            "outcome": "accept",
            "question_text": ["1. How does warm air usually move?"],
            "placement": "inline",
            "region_kind": "answer_line_group",
        },
        style="lines",
    ),
    Fixture(
        fixture_id="rectangular-answer-boxes",
        filename="05-rectangular-answer-boxes.pdf",
        title="Reading Response",
        pages=(("1. What choice changes the main character?",),),
        expected={
            "outcome": "accept",
            "question_text": ["1. What choice changes the main character?"],
            "placement": "inline",
            "region_kind": "safe_box",
        },
        style="boxes",
    ),
    Fixture(
        fixture_id="multi-page-order",
        filename="06-multi-page-order.pdf",
        title="Earth Systems",
        pages=(
            ("1. How does water enter the atmosphere?", "2. What forms when vapor cools?"),
            ("3. Why does water flow downhill?", "4. Where can groundwater collect?"),
        ),
        expected={
            "outcome": "accept",
            "question_text": [
                "1. How does water enter the atmosphere?",
                "2. What forms when vapor cools?",
                "3. Why does water flow downhill?",
                "4. Where can groundwater collect?",
            ],
            "placement": "inline",
        },
    ),
    Fixture(
        fixture_id="long-answer-appendix",
        filename="07-long-answer-appendix.pdf",
        title="Evidence Explanation",
        pages=(("1. Explain how the evidence supports the claim.",),),
        expected={
            "outcome": "accept",
            "question_text": ["1. Explain how the evidence supports the claim."],
            "placement": "appendix",
            "sample_answer": " ".join(["Evidence must remain exact and readable."] * 80),
        },
    ),
    Fixture(
        fixture_id="unicode-punctuation-names",
        filename="08-unicode-punctuation-names.pdf",
        title="Voices in Literature",
        pages=(
            (
                "1. Why does Zoë call the decision “unfair”—and what changes?",
                "2. What does José’s response reveal?",  # noqa: RUF001 - corpus Unicode
            ),
        ),
        expected={
            "outcome": "accept",
            "question_text": [
                "1. Why does Zoë call the decision “unfair”—and what changes?",
                "2. What does José’s response reveal?",  # noqa: RUF001 - corpus Unicode
            ],
            "placement": "inline",
        },
        unicode_font=True,
    ),
    Fixture(
        fixture_id="rotated-crop-box",
        filename="09-rotated-crop-box.pdf",
        title="Transform Evidence",
        pages=(("1. What pattern appears in the data?",),),
        expected={
            "outcome": "accept",
            "question_text": ["1. What pattern appears in the data?"],
            "placement": "appendix",
            "ambiguity_flags": ["non_default_crop_box", "non_identity_rotation"],
        },
        rotate=90,
        crop=True,
    ),
    Fixture(
        fixture_id="no-safe-inline-region",
        filename="10-no-safe-inline-region.pdf",
        title="Compact Source Analysis",
        pages=(("1. State the author’s central claim.",),),  # noqa: RUF001 - corpus Unicode
        expected={
            "outcome": "accept",
            "question_text": [
                "1. State the author’s central claim."  # noqa: RUF001 - corpus Unicode
            ],
            "placement": "appendix",
        },
        style="dense",
        unicode_font=True,
    ),
    Fixture(
        fixture_id="controlled-scan-rejection",
        filename="11-controlled-scan-rejection.pdf",
        title="Scanned Worksheet",
        pages=((),),
        expected={"outcome": "reject", "error_code": "requires_ocr"},
        style="scan",
    ),
    Fixture(
        fixture_id="ambiguous-question-boundary",
        filename="12-ambiguous-question-boundary.pdf",
        title="Reflection Notes",
        pages=(
            (
                "Use the ideas below to respond in complete sentences.",
                "Community choices affect people in different ways",
                "Evidence can support more than one interpretation",
            ),
        ),
        expected={"outcome": "reject", "error_code": "ambiguous_question_boundaries"},
        style="plain",
    ),
)


def _png_bytes() -> bytes:
    width, height = 96, 48
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(35 if (x + y) % 11 < 2 else 242 for x in range(width))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + chunk(b"IEND", b"")
    )


def _base_pdf(fixture: Fixture) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1, pageCompression=1)
    font_name = "Helvetica"
    if fixture.unicode_font:
        font_name = "CorpusNotoSans"
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_name, str(NOTO_REGULAR)))
    for page_index, questions in enumerate(fixture.pages):
        if fixture.style == "scan":
            pdf.drawImage(ImageReader(io.BytesIO(_png_bytes())), 54, 330, width=504, height=252)
            pdf.showPage()
            continue
        pdf.setFont(font_name, 16)
        pdf.drawString(54, 742, fixture.title)
        pdf.setFont(font_name, 9)
        pdf.drawRightString(558, 744, f"Page {page_index + 1}")
        y = 690
        for question in questions:
            pdf.setFont(font_name, 12)
            pdf.drawString(54, y, question)
            if fixture.style == "boxes":
                pdf.rect(54, y - 92, 504, 72, stroke=1, fill=0)
                y -= 138
            elif fixture.style == "dense":
                pdf.setFont(font_name, 9)
                for line_index in range(15):
                    pdf.drawString(
                        54,
                        y - 16 - (line_index * 14),
                        "Reference material occupies this verified source area.",
                    )
                y -= 245
            elif fixture.style == "plain":
                y -= 34
            else:
                for offset in (34, 54, 74):
                    pdf.line(54, y - offset, 558, y - offset)
                y -= 128
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def _transform(source: bytes, fixture: Fixture) -> bytes:
    if not fixture.rotate and not fixture.crop:
        return source
    reader = PdfReader(io.BytesIO(source), strict=True)
    writer = PdfWriter()
    for page in reader.pages:
        if fixture.rotate:
            page.rotate(fixture.rotate)
        if fixture.crop:
            page.cropbox.lower_left = (18, 18)
            page.cropbox.upper_right = (594, 774)
        writer.add_page(page)
    writer.add_metadata({"/Producer": GENERATOR_VERSION})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def build_fixture(fixture: Fixture) -> bytes:
    return _transform(_base_pdf(fixture), fixture)


def build_manifest(payloads: dict[str, bytes]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "license": "Synthetic test fixtures; project-authored and free of student data.",
        "fixtures": [
            {
                "fixture_id": fixture.fixture_id,
                "file": fixture.filename,
                "sha256": hashlib.sha256(payloads[fixture.filename]).hexdigest(),
                "size_bytes": len(payloads[fixture.filename]),
                "expected": fixture.expected,
            }
            for fixture in FIXTURES
        ],
    }


def canonical_manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def generate(*, check: bool) -> None:
    payloads = {fixture.filename: build_fixture(fixture) for fixture in FIXTURES}
    manifest_bytes = canonical_manifest_bytes(build_manifest(payloads))
    if check:
        for filename, payload in payloads.items():
            if (CORPUS_DIR / filename).read_bytes() != payload:
                raise SystemExit(f"gold corpus drift: {filename}")
        if MANIFEST_PATH.read_bytes() != manifest_bytes:
            raise SystemExit("gold corpus manifest drift")
        return
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, payload in payloads.items():
        (CORPUS_DIR / filename).write_bytes(payload)
    MANIFEST_PATH.write_bytes(manifest_bytes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    generate(check=options.check)


if __name__ == "__main__":
    main()
