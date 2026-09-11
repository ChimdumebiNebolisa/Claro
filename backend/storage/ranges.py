"""Strict parser for the one HTTP byte range supported by PDF streaming."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.storage.errors import RangeNotSatisfiable

_SINGLE_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)
MAX_RANGE_HEADER_LENGTH = 128


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int
    total_size: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.end}/{self.total_size}"


def parse_byte_range(header: str, total_size: int) -> ByteRange:
    """Parse and normalize one satisfiable RFC 9110 byte range.

    Multi-range responses are deliberately unsupported. An explicit end past
    EOF is clipped as required; a start at or past EOF is unsatisfiable.
    """

    if isinstance(total_size, bool) or total_size <= 0:
        raise RangeNotSatisfiable("the object has no satisfiable byte range")
    if not isinstance(header, str) or not header or len(header) > MAX_RANGE_HEADER_LENGTH:
        raise RangeNotSatisfiable("the byte range is invalid")
    match = _SINGLE_RANGE.fullmatch(header.strip())
    if match is None:
        raise RangeNotSatisfiable("only one bytes range is supported")
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise RangeNotSatisfiable("the byte range is empty")
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise RangeNotSatisfiable("the suffix range is invalid")
            length = min(suffix_length, total_size)
            return ByteRange(total_size - length, total_size - 1, total_size)
        start = int(start_text)
        if start >= total_size:
            raise RangeNotSatisfiable("the byte range starts after the object")
        end = total_size - 1 if not end_text else min(int(end_text), total_size - 1)
    except ValueError as exc:
        raise RangeNotSatisfiable("the byte range is invalid") from exc
    if end < start:
        raise RangeNotSatisfiable("the byte range is reversed")
    return ByteRange(start, end, total_size)
