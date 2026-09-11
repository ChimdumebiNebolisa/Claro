from __future__ import annotations

import pytest

from backend.storage import (
    InvalidObjectKey,
    RangeNotSatisfiable,
    assignment_manifest_object_key,
    export_manifest_object_key,
    export_pdf_object_key,
    parse_byte_range,
    physical_ir_object_key,
    preview_object_key,
    source_object_key,
    validate_object_key,
)


def test_authoritative_object_layout() -> None:
    assignment_id = "asg_abc-123"
    export_id = "exp_4_deadbeef"
    assert source_object_key(assignment_id) == ("assignments/asg_abc-123/source/original.pdf")
    assert physical_ir_object_key(assignment_id) == (
        "assignments/asg_abc-123/analysis/physical-ir.json"
    )
    assert assignment_manifest_object_key(assignment_id) == (
        "assignments/asg_abc-123/manifest/assignment.json"
    )
    assert preview_object_key(assignment_id, 8).endswith("/previews/page-8.png")
    assert export_pdf_object_key(assignment_id, export_id).endswith(
        "/exports/exp_4_deadbeef/completed.pdf"
    )
    assert export_manifest_object_key(assignment_id, export_id).endswith(
        "/exports/exp_4_deadbeef/manifest.json"
    )


@pytest.mark.parametrize(
    "value",
    [
        "../escape",
        "assignments/../escape",
        "assignments\\escape",
        "/absolute/path",
        "C:/drive/path",
        "assignments//object",
        "assignments/.hidden",
        "assignments/object/",
        "assignments/\x00/object",
    ],
)
def test_object_keys_reject_traversal_and_ambiguous_paths(value: str) -> None:
    with pytest.raises(InvalidObjectKey):
        validate_object_key(value)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-0", (0, 0)),
        ("bytes=0-4", (0, 4)),
        ("bytes=5-", (5, 9)),
        ("bytes=-3", (7, 9)),
        ("bytes=-30", (0, 9)),
        ("BYTES=8-99", (8, 9)),
    ],
)
def test_single_byte_ranges_are_normalized(header: str, expected: tuple[int, int]) -> None:
    parsed = parse_byte_range(header, 10)
    assert (parsed.start, parsed.end) == expected
    assert parsed.length == expected[1] - expected[0] + 1
    assert parsed.content_range == f"bytes {expected[0]}-{expected[1]}/10"


@pytest.mark.parametrize(
    "header",
    [
        "items=0-1",
        "bytes=",
        "bytes=-",
        "bytes=-0",
        "bytes=9-4",
        "bytes=10-",
        "bytes=0-1,4-5",
        "bytes =0-1",
        "bytes=one-two",
        "bytes=" + "9" * 200 + "-",
    ],
)
def test_invalid_or_unsatisfiable_ranges_fail_closed(header: str) -> None:
    with pytest.raises(RangeNotSatisfiable):
        parse_byte_range(header, 10)


def test_empty_object_has_no_satisfiable_range() -> None:
    with pytest.raises(RangeNotSatisfiable):
        parse_byte_range("bytes=0-", 0)
