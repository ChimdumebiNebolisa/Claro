"""Vendored Noto Sans registration and exact glyph coverage checks."""

from __future__ import annotations

import threading
import unicodedata
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from backend.document.errors import document_error

FONT_ROOT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "noto-sans"
REGULAR_FONT_PATH = FONT_ROOT / "NotoSans-Regular.ttf"
BOLD_FONT_PATH = FONT_ROOT / "NotoSans-Bold.ttf"
REGULAR_FONT_NAME = "ClarosNotoSans"
BOLD_FONT_NAME = "ClarosNotoSans-Bold"

_registration_lock = threading.Lock()
_registered = False


def register_fonts() -> None:
    global _registered
    if _registered:
        return
    with _registration_lock:
        if _registered:
            return
        if not REGULAR_FONT_PATH.is_file() or not BOLD_FONT_PATH.is_file():
            raise RuntimeError("Vendored Noto Sans assets are missing")
        pdfmetrics.registerFont(TTFont(REGULAR_FONT_NAME, str(REGULAR_FONT_PATH)))
        pdfmetrics.registerFont(TTFont(BOLD_FONT_NAME, str(BOLD_FONT_PATH)))
        _registered = True


def ensure_supported_text(text: str, *, bold: bool = False) -> None:
    """Reject controls and glyphs that the configured embedded font cannot map."""

    register_fonts()
    font_name = BOLD_FONT_NAME if bold else REGULAR_FONT_NAME
    face = pdfmetrics.getFont(font_name).face
    character_map = face.charToGlyph
    for character in text:
        if character in {"\n", "\r"}:
            continue
        category = unicodedata.category(character)
        if category in {"Cc", "Cs"}:
            raise document_error("unsupported_glyph")
        codepoint = ord(character)
        if codepoint not in character_map or character_map[codepoint] == 0:
            raise document_error("unsupported_glyph")
