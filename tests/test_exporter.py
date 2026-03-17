"""Tests for exporter module: PDF export with questions and answers."""
import fitz

from exporter import build_export_pdf


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text from PDF bytes."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return " ".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_build_export_pdf_returns_bytes():
    """build_export_pdf returns non-empty PDF bytes."""
    questions = [{"id": 1, "text": "What is 2+2?"}, {"id": 2, "text": "What is 3+3?"}]
    answers = [
        {"question_id": 1, "answer_text": "4"},
        {"question_id": 2, "answer_text": "6"},
    ]
    pdf_bytes = build_export_pdf("Test Assignment", questions, answers)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 100
    assert pdf_bytes.startswith(b"%PDF")


def test_build_export_pdf_includes_title_and_answers():
    """Exported PDF contains assignment title and written answers."""
    questions = [{"id": 1, "text": "Solve for x."}]
    answers = [{"question_id": 1, "answer_text": "x = 5"}]
    pdf_bytes = build_export_pdf("Algebra Quiz", questions, answers)
    text = _pdf_text(pdf_bytes)
    assert "Algebra" in text
    assert "x = 5" in text


def test_build_export_pdf_no_answer_shows_placeholder():
    """Missing answer is rendered as (No answer)."""
    questions = [{"id": 1, "text": "Question one."}]
    answers = []  # no answers
    pdf_bytes = build_export_pdf("Title", questions, answers)
    text = _pdf_text(pdf_bytes)
    assert "No answer" in text


def test_build_export_pdf_strips_latex_dollars():
    """LaTeX $...$ in answer_text is stripped to plain text in PDF."""
    questions = [{"id": 1, "text": "Solve for x."}]
    answers = [{"question_id": 1, "answer_text": "$x = 5$"}]
    pdf_bytes = build_export_pdf("Math", questions, answers)
    text = _pdf_text(pdf_bytes)
    assert "x = 5" in text
