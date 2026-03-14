"""
PDF question extraction for Claros. Handles PDFs where questions are on lines
starting with "Question 1:", "Question 2:", etc. Falls back to full text as
single block (id=0) if no such lines are found.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import fitz  # PyMuPDF


@dataclass
class Question:
    id: int
    text: str


# Line starting with "Question N:" (case insensitive). Captures N and rest of line.
_QUESTION_LINE_RE = re.compile(r"^\s*Question\s*(\d+)\s*:\s*(.*)", re.IGNORECASE)


def _extract_lines_with_size(doc: fitz.Document) -> List[tuple[str, float]]:
    """Extract (line_text, font_size) for each line from PDF. Uses first span size per line."""
    lines: List[tuple[str, float]] = []
    for page in doc:
        block_dict = page.get_text("dict", sort=True)
        for block in block_dict.get("blocks", []):
            for line in block.get("lines", []):
                line_text_parts = []
                line_size = None
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if text:
                        line_text_parts.append(text)
                        if line_size is None and "size" in span:
                            line_size = span["size"]
                if line_text_parts:
                    text = " ".join(line_text_parts).strip()
                    if text:
                        lines.append((text, line_size if line_size is not None else 0.0))
    return lines


def parse_pdf(pdf_path: str | Path) -> tuple[str, List[Question]]:
    """
    Parse PDF and extract questions. Expects lines like "Question 1: ...", "Question 2: ...".
    Returns (title, questions). Title is the first line. If no "Question N:" lines found,
    returns one question with id=0 and full text.
    """
    path = Path(pdf_path)
    doc = fitz.open(path)
    try:
        lines_with_size = _extract_lines_with_size(doc)
        lines = [t for t, _ in lines_with_size]
        full_text = "\n".join(lines).strip() or "(No extractable text)"

        if not lines:
            title = path.stem
            result = title, [Question(id=0, text=full_text)]
            print(f"[parser.py] No lines extracted. Returning: title={title!r}, 1 question (id=0)")
            return result

        title = lines[0].strip()[:80] if lines else path.stem
        questions: List[Question] = []
        i = 0

        while i < len(lines):
            m = _QUESTION_LINE_RE.match(lines[i])
            if m:
                qid = int(m.group(1))
                # Strip "Question N:" prefix; rest of line is start of question text
                text_parts = [m.group(2).strip()] if m.group(2).strip() else []
                i += 1
                # Collect lines until the next "Question N:" line
                while i < len(lines) and not _QUESTION_LINE_RE.match(lines[i]):
                    text_parts.append(lines[i])
                    i += 1
                q_text = "\n".join(text_parts).strip()
                questions.append(Question(id=qid, text=q_text))
            else:
                i += 1

        if not questions:
            result = title, [Question(id=0, text=full_text)]
            print(f"[parser.py] No 'Question N:' lines found. Fallback: title={title!r}, 1 question (id=0)")
            return result

        print(f"[parser.py] Returning: title={title!r}, {len(questions)} questions: {[(q.id, q.text[:60] + ('...' if len(q.text) > 60 else '')) for q in questions]}")
        return title, questions
    finally:
        doc.close()
