"""Shared extracted worksheet fixtures."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.document import QuestionEvidence, extract_physical_ir
from backend.document.models import PhysicalDocumentIR
from backend.tests.document.factories import worksheet_pdf


@dataclass(frozen=True, slots=True)
class ExtractedWorksheet:
    source: bytes
    document: PhysicalDocumentIR
    questions: tuple[QuestionEvidence, ...]


@pytest.fixture(scope="module")
def extracted_worksheet() -> ExtractedWorksheet:
    source = worksheet_pdf()
    document = extract_physical_ir(source)
    prompt_blocks = tuple(
        block
        for block in document.pages[0].blocks
        if block.kind == "text" and block.text and block.text.rstrip().endswith("?")
    )
    assert len(prompt_blocks) == 2
    questions = tuple(
        QuestionEvidence(
            question_id=f"question-{index}",
            display_identifier=f"Question {index}",
            prompt_block_ids=(block.id,),
        )
        for index, block in enumerate(prompt_blocks, start=1)
    )
    return ExtractedWorksheet(source=source, document=document, questions=questions)
