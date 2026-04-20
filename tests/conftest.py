"""Pytest configuration and shared fixtures."""
import tempfile
from pathlib import Path

import fitz
import pytest


@pytest.fixture
def tmp_pdf_question_format(tmp_path):
    """Create a minimal PDF with 'Question N:' lines for parser tests."""
    path = tmp_path / "assignment.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # PyMuPDF get_text("dict") returns lines from spans; we need separate text blocks/lines
    page.insert_text((72, 72), "Math Assignment", fontsize=14)
    page.insert_text((72, 100), "Question 1: Solve for x: 3x + 7 = 22", fontsize=12)
    page.insert_text((72, 120), "Question 2: Solve for x: 2(x - 4) = 10", fontsize=12)
    page.insert_text((72, 140), "Question 3: Word problem here.", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def tmp_pdf_numbered_format(tmp_path):
    """Create a minimal PDF with '1.', '2.' numbered lines for parser tests."""
    path = tmp_path / "numbered.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Worksheet", fontsize=14)
    page.insert_text((72, 100), "1. First question text", fontsize=12)
    page.insert_text((72, 120), "2. Second question text", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def tmp_pdf_no_questions(tmp_path):
    """Create a PDF with no Question N: or N. pattern (fallback to single block)."""
    path = tmp_path / "plain.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Just a paragraph of text with no question format.", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def tmp_pdf_question_double_digit(tmp_path):
    """PDF with Question 10: to validate double-digit question ids."""
    path = tmp_path / "double_digit.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Quiz", fontsize=14)
    page.insert_text((72, 100), "Question 1: First item", fontsize=12)
    page.insert_text((72, 120), "Question 10: Tenth item body", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def tmp_pdf_question_multiline(tmp_path):
    """Question 1: spans two visual lines (continuation merged into Q1)."""
    path = tmp_path / "multiline.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sheet", fontsize=14)
    page.insert_text((72, 100), "Question 1: Start of problem", fontsize=12)
    page.insert_text((72, 120), "continuation line without question prefix", fontsize=12)
    page.insert_text((72, 140), "Question 2: Second problem", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def tmp_pdf_numbered_with_continuation(tmp_path):
    """Numbered 1. / 2. with a continuation line absorbed into question 1."""
    path = tmp_path / "numbered_continue.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Worksheet B", fontsize=14)
    page.insert_text((72, 100), "1. Alpha prompt", fontsize=12)
    page.insert_text((72, 120), "Extra detail for item one", fontsize=12)
    page.insert_text((72, 140), "2. Beta prompt", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path
