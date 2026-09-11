"""Stable, content-free document engine failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentFailure:
    code: str
    message: str
    recoverable: bool = True


class DocumentEngineError(ValueError):
    """An expected PDF rejection safe to translate into the API envelope.

    The exception deliberately carries no worksheet or answer content. Callers
    may log ``code`` but must not log the originating parser exception.
    """

    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        self.failure = DocumentFailure(code=code, message=message, recoverable=recoverable)
        super().__init__(code)

    @property
    def code(self) -> str:
        return self.failure.code

    @property
    def safe_message(self) -> str:
        return self.failure.message

    @property
    def recoverable(self) -> bool:
        return self.failure.recoverable


SAFE_MESSAGES = {
    "invalid_pdf_signature": "This file is not a readable PDF.",
    "file_too_large": "This PDF is larger than the 10 MiB limit.",
    "empty_pdf": "This PDF does not contain any pages.",
    "page_limit_exceeded": "Claros V2 supports worksheets with up to 8 pages.",
    "question_limit_exceeded": "Claros V2 supports worksheets with up to 40 questions.",
    "encrypted_pdf": "Password-protected or encrypted PDFs are not supported.",
    "malformed_pdf": "This PDF could not be read safely.",
    "requires_ocr": "This PDF appears to be scanned. Claros V2 supports PDFs with selectable text.",
    "extracted_text_limit_exceeded": (
        "This worksheet contains more text than Claros V2 can safely analyze."
    ),
    "invalid_physical_evidence": "This PDF contains page geometry that Claros cannot safely use.",
    "unsafe_question_evidence": "Claros could not safely match this question.",
    "ambiguous_question_boundaries": (
        "Claros could not safely distinguish the worksheet questions."
    ),
    "unsupported_glyph": "This answer contains a character the PDF font cannot render safely.",
    "stale_source": "The worksheet source changed after review. Review the answer again.",
    "stale_physical_ir": "The worksheet analysis changed after review. Review the answer again.",
    "placement_changed": "The answer placement changed after review. Review the answer again.",
    "no_confirmed_answers": "Confirm at least one answer before exporting.",
    "invalid_export": "The completed PDF could not be validated safely.",
    "publish_failed": "The completed PDF could not be saved. Try again.",
}


def document_error(code: str, *, recoverable: bool = True) -> DocumentEngineError:
    return DocumentEngineError(
        code,
        SAFE_MESSAGES.get(code, "Claros could not process this PDF safely."),
        recoverable=recoverable,
    )
