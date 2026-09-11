"""Generate validator-differential and latency evidence for the OpenPDF spike.

This is test infrastructure, not an export implementation. Test-only pikepdf
mutations create known-bad derivatives; pikepdf never renders an output.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pikepdf

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(__file__).resolve().parent
INTEGRATION = ROOT / "experiments" / "openpdf-integration"
HOSTILE = ROOT / "experiments" / "openpdf-hostile"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(INTEGRATION))

from openpdf_integration.adapter import _process_rss  # noqa: E402
from openpdf_integration.contract import (  # noqa: E402
    ContinuationInstruction,
    GeneratedLine,
    PageGeometry,
    PdfRenderJob,
    RenderAnswer,
    ResourceLimits,
    SourceBinding,
    WorkerSuccess,
)

from backend.document import extract_physical_ir  # noqa: E402
from backend.document.models import sha256_hex  # noqa: E402
from backend.document.preflight import PreflightLimits  # noqa: E402
from backend.tests.document.factories import worksheet_pdf  # noqa: E402

Gate = Literal["full", "qpdf_pdfbox", "pdfbox_only"]

JAR = INTEGRATION / "target" / "openpdf-integration-0.1.0-SNAPSHOT-all.jar"
FONT_ROOT = ROOT / "assets" / "fonts" / "noto-sans"
FONT = FONT_ROOT / "NotoSans-Regular.ttf"
PDFJS = INTEGRATION / "scripts" / "validate-pdfjs.mjs"
QPDF = HOSTILE / ".tools" / "qpdf" / "bin" / "qpdf.exe"
JAVA = Path(shutil.which("java") or "java")
NODE = Path(shutil.which("node") or "node")


@dataclass(frozen=True, slots=True)
class ProcessRun:
    duration_ms: int
    peak_rss_bytes: int | None
    return_code: int


def _run(command: Sequence[str], *, cwd: Path, timeout: float = 120) -> ProcessRun:
    options: dict[str, Any] = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    started = time.perf_counter()
    process = subprocess.Popen(list(command), **options)  # noqa: S603
    peak: int | None = None
    deadline = started + timeout
    try:
        while process.poll() is None:
            current = _process_rss(process.pid)
            if current is not None:
                peak = max(peak or 0, current)
            if time.perf_counter() >= deadline:
                process.kill()
                raise TimeoutError(f"process timed out: {command[0]}")
            time.sleep(0.01)
        return ProcessRun(
            duration_ms=round((time.perf_counter() - started) * 1000),
            peak_rss_bytes=peak,
            return_code=int(process.returncode),
        )
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def _font_sha256() -> str:
    return sha256_hex(FONT.read_bytes())


def _page_geometry(source: bytes) -> tuple[Any, tuple[PageGeometry, ...]]:
    physical = extract_physical_ir(source, limits=PreflightLimits(max_pages=100))
    pages = tuple(
        PageGeometry(
            page_number=page.page_index + 1,
            media_box_mpt=tuple(page.media_box_mpt.to_list()),
            crop_box_mpt=tuple(page.crop_box_mpt.to_list()),
            rotation=page.rotation,
            user_unit=page.user_unit,
            canonical_to_pdf_mpt=tuple(page.canonical_to_pdf_mpt.to_list()),
        )
        for page in physical.pages
    )
    return physical, pages


def _line_answer(
    identifier: str,
    text: str,
    *,
    page_number: int = 1,
    x_mpt: int = 72_000,
    baseline_y_mpt: int = 120_000,
) -> RenderAnswer:
    digest = sha256_hex(text.encode("utf-8"))
    return RenderAnswer(
        question_id=f"question_{identifier.lower()}",
        display_identifier=identifier,
        committed_text=text,
        committed_text_sha256=digest,
        placement_hash=sha256_hex(f"placement:{identifier}:{digest}".encode()),
        placement_classification="inline",
        page_number=page_number,
        lines=(
            GeneratedLine(
                text=text,
                separator_after="",
                x_mpt=x_mpt,
                baseline_y_mpt=baseline_y_mpt,
                font_size_mpt=11_000,
            ),
        ),
    )


def _appendix_answer(identifier: str, text: str, *, page_number: int = 1) -> RenderAnswer:
    paragraphs = tuple(text.split("\n\n"))
    digest = sha256_hex(text.encode("utf-8"))
    return RenderAnswer(
        question_id=f"question_{identifier.lower()}",
        display_identifier=identifier,
        committed_text=text,
        committed_text_sha256=digest,
        placement_hash=sha256_hex(f"appendix:{identifier}:{digest}".encode()),
        placement_classification="appendix",
        page_number=page_number,
        continuation=ContinuationInstruction(
            worksheet_title="Synthetic validator worksheet",
            source_question=f"Synthetic source question {identifier}?",
            source_page_number=page_number,
            paragraphs=paragraphs,
        ),
    )


def _multiline_answer(
    identifier: str,
    first: str,
    second: str,
    *,
    page_number: int,
    baseline_y_mpt: int,
) -> RenderAnswer:
    text = f"{first} {second}"
    digest = sha256_hex(text.encode("utf-8"))
    return RenderAnswer(
        question_id=f"question_{identifier.lower()}",
        display_identifier=identifier,
        committed_text=text,
        committed_text_sha256=digest,
        placement_hash=sha256_hex(f"placement:{identifier}:{digest}".encode()),
        placement_classification="inline",
        page_number=page_number,
        lines=(
            GeneratedLine(
                text=first,
                separator_after=" ",
                x_mpt=72_000,
                baseline_y_mpt=baseline_y_mpt,
                font_size_mpt=11_000,
            ),
            GeneratedLine(
                text=second,
                separator_after="",
                x_mpt=72_000,
                baseline_y_mpt=baseline_y_mpt + 15_000,
                font_size_mpt=11_000,
            ),
        ),
    )


def _job(source: bytes, answers: Sequence[RenderAnswer]) -> PdfRenderJob:
    physical, pages = _page_geometry(source)
    return PdfRenderJob(
        schema_version=1,
        operation="render",
        job_id=f"job_{uuid.uuid4().hex}",
        source=SourceBinding(
            source_id=f"source_{physical.source_sha256[:24]}",
            sha256=physical.source_sha256,
            size_bytes=len(source),
            page_count=len(pages),
            physical_ir_sha256=physical.ir_sha256,
            evidence_version=f"{physical.parser_version}:{physical.schema_version}",
        ),
        limits=ResourceLimits(
            max_input_bytes=max(10 * 1024 * 1024, len(source) + 1),
            max_output_bytes=128 * 1024 * 1024,
            max_pages=max(100, len(pages)),
        ),
        font_id="noto-sans-regular-v1",
        font_sha256=_font_sha256(),
        pages=pages,
        answers=tuple(answers),
    )


def _write_job(root: Path, source: bytes, job: PdfRenderJob) -> None:
    root.mkdir(parents=True)
    (root / "tmp").mkdir()
    (root / "source.pdf").write_bytes(source)
    (root / "job.json").write_bytes(job.canonical_bytes())


def _worker_command(root: Path) -> tuple[str, ...]:
    return (
        str(JAVA),
        "-Djava.awt.headless=true",
        f"-Djava.io.tmpdir={root / 'tmp'}",
        "-Xms16m",
        "-Xmx192m",
        "-jar",
        str(JAR),
        "--job-dir",
        str(root),
        "--font-dir",
        str(FONT_ROOT),
    )


def _pdfbox_command(root: Path) -> tuple[str, ...]:
    return (
        str(JAVA),
        "-Djava.awt.headless=true",
        f"-Djava.io.tmpdir={root / 'tmp'}",
        "-Xms16m",
        "-Xmx192m",
        "-cp",
        str(JAR),
        "org.claros.openpdfintegration.PdfBoxValidatorMain",
        "--job-dir",
        str(root),
    )


def _render(root: Path) -> ProcessRun:
    result = _run(_worker_command(root), cwd=root)
    status = json.loads((root / "worker-status.json").read_text(encoding="utf-8"))
    if result.return_code != 0 or status.get("status") != "ok":
        raise RuntimeError(f"OpenPDF test fixture render failed: {status.get('code', 'exit')}")
    return result


def _validator(root: Path, name: Literal["qpdf", "pdfbox", "pdfjs"]) -> dict[str, Any]:
    status_path = root / f"{name}-status.json"
    status_path.unlink(missing_ok=True)
    if name == "qpdf":
        run = _run((str(QPDF), "--check", str(root / "quarantine" / "derivative.pdf")), cwd=root)
        return {
            "accepted": run.return_code == 0,
            "code": "ok" if run.return_code == 0 else "qpdf_check",
            "duration_ms": run.duration_ms,
            "peak_rss_bytes": run.peak_rss_bytes,
        }
    command = _pdfbox_command(root) if name == "pdfbox" else (str(NODE), str(PDFJS), str(root))
    run = _run(command, cwd=root)
    status: dict[str, Any]
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        status = {"status": "fail", "code": "missing_status"}
    return {
        "accepted": run.return_code == 0 and status.get("status") == "ok",
        "code": status.get("code", "ok" if status.get("status") == "ok" else "process_exit"),
        "duration_ms": run.duration_ms,
        "peak_rss_bytes": run.peak_rss_bytes,
    }


def _copy_case(destination: Path, source_root: Path) -> None:
    destination.mkdir(parents=True)
    (destination / "tmp").mkdir()
    (destination / "quarantine").mkdir()
    shutil.copy2(source_root / "source.pdf", destination / "source.pdf")
    shutil.copy2(source_root / "job.json", destination / "job.json")
    shutil.copy2(
        source_root / "quarantine" / "derivative.pdf",
        destination / "quarantine" / "derivative.pdf",
    )


def _save_pdf(path: Path, mutate: Callable[[pikepdf.Pdf], None]) -> None:
    temporary = path.with_suffix(".mutated.pdf")
    with pikepdf.Pdf.open(path, attempt_recovery=False) as pdf:
        mutate(pdf)
        pdf.save(temporary)
    temporary.replace(path)


def _altered_derivative(
    root: Path,
    source: bytes,
    expected: PdfRenderJob,
    alter: Callable[[dict[str, Any]], None],
) -> None:
    raw = expected.model_dump(mode="json")
    alter(raw)
    changed = PdfRenderJob.from_bytes(
        (json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    )
    _write_job(root, source, changed)
    _render(root)
    (root / "job.json").write_bytes(expected.canonical_bytes())


def _simple_base(root: Path, source: bytes | None = None) -> tuple[bytes, PdfRenderJob]:
    payload = source or worksheet_pdf(page_count=2)
    job = _job(payload, (_line_answer("Q1", "The office keeps exact committed text."),))
    _write_job(root, payload, job)
    _render(root)
    return payload, job


def _feature_base(root: Path, fixture: str) -> tuple[bytes, PdfRenderJob]:
    source = (HOSTILE / "target" / "fixtures" / f"{fixture}.pdf").read_bytes()
    return _simple_base(root, source)


def _prepare_differential(root: Path) -> list[tuple[str, Path, str]]:
    cases: list[tuple[str, Path, str]] = []
    base = root / "base"
    source, job = _simple_base(base)

    valid = root / "valid_control"
    _copy_case(valid, base)
    cases.append(("valid_control", valid, "accept"))

    malformed = root / "malformed_structure"
    _copy_case(malformed, base)
    derivative = malformed / "quarantine" / "derivative.pdf"
    payload = derivative.read_bytes()
    derivative.write_bytes(payload[: max(32, len(payload) // 2)])
    cases.append(("malformed_structure", malformed, "reject"))

    words = ("office", "official", "efficient", "file", "first", "affinity", "different")
    ligature_source = (
        HOSTILE / "target" / "office-investigation" / "minimal-source.pdf"
    ).read_bytes()
    ligature_lines = tuple(
        GeneratedLine(
            text=word,
            separator_after="\n" if index < len(words) - 1 else "",
            x_mpt=72_000,
            baseline_y_mpt=(142 + index * 28) * 1000,
            font_size_mpt=14_000,
        )
        for index, word in enumerate(words)
    )
    committed = "\n".join(words)
    ligature_answer = RenderAnswer(
        question_id="question_ligature",
        display_identifier="LIGATURE",
        committed_text=committed,
        committed_text_sha256=sha256_hex(committed.encode()),
        placement_hash=sha256_hex(b"ligature-placement"),
        placement_classification="inline",
        page_number=1,
        lines=ligature_lines,
    )
    ligature_job = _job(ligature_source, (ligature_answer,))
    ligature = root / "ligature_bad_tounicode"
    ligature.mkdir(parents=True)
    (ligature / "tmp").mkdir()
    (ligature / "quarantine").mkdir()
    (ligature / "source.pdf").write_bytes(ligature_source)
    (ligature / "job.json").write_bytes(ligature_job.canonical_bytes())
    shutil.copy2(
        HOSTILE / "target" / "office-investigation" / "minimal-default-fop.pdf",
        ligature / "quarantine" / "derivative.pdf",
    )
    cases.append(("ligature_bad_tounicode", ligature, "reject"))

    wrong_text = root / "wrong_generated_text"

    def alter_text(raw: dict[str, Any]) -> None:
        text = "A syntactically valid but wrong generated answer."
        answer = raw["answers"][0]
        answer["committed_text"] = text
        answer["committed_text_sha256"] = sha256_hex(text.encode())
        answer["lines"][0]["text"] = text

    _altered_derivative(wrong_text, source, job, alter_text)
    cases.append(("wrong_generated_text", wrong_text, "reject"))

    missing = root / "missing_generated_text"
    _copy_case(missing, base)

    def remove_generated(pdf: pikepdf.Pdf) -> None:
        contents = pdf.pages[0].obj["/Contents"]
        if isinstance(contents, pikepdf.Array):
            del contents[-1]
        else:
            del pdf.pages[0].obj["/Contents"]

    _save_pdf(missing / "quarantine" / "derivative.pdf", remove_generated)
    cases.append(("missing_generated_text", missing, "reject"))

    wrong_coordinate = root / "incorrect_physical_coordinates"

    def alter_coordinate(raw: dict[str, Any]) -> None:
        raw["answers"][0]["lines"][0]["x_mpt"] += 50_000

    _altered_derivative(wrong_coordinate, source, job, alter_coordinate)
    cases.append(("incorrect_physical_coordinates", wrong_coordinate, "reject"))

    crop = root / "page_box_mutation"
    _copy_case(crop, base)
    _save_pdf(
        crop / "quarantine" / "derivative.pdf",
        lambda pdf: pdf.pages[0].obj.__setitem__("/CropBox", pikepdf.Array([12, 12, 600, 780])),
    )
    cases.append(("page_box_mutation", crop, "reject"))

    rotation = root / "page_rotation_mutation"
    _copy_case(rotation, base)
    _save_pdf(
        rotation / "quarantine" / "derivative.pdf",
        lambda pdf: pdf.pages[0].obj.__setitem__("/Rotate", 90),
    )
    cases.append(("page_rotation_mutation", rotation, "reject"))

    stream = root / "source_content_stream_mutation"
    _copy_case(stream, base)

    def remove_source_stream(pdf: pikepdf.Pdf) -> None:
        contents = pdf.pages[0].obj["/Contents"]
        if isinstance(contents, pikepdf.Array):
            del contents[0]
        else:
            del pdf.pages[0].obj["/Contents"]

    _save_pdf(stream / "quarantine" / "derivative.pdf", remove_source_stream)
    cases.append(("source_content_stream_mutation", stream, "reject"))

    for case_name, fixture, mutation in (
        ("annotation_mutation", "annotations", "annotations"),
        ("form_mutation", "acroform", "form"),
        ("link_mutation", "links", "annotations"),
        ("outline_mutation", "outlines", "outlines"),
    ):
        feature_base = root / f"{case_name}_base"
        _feature_base(feature_base, fixture)
        case = root / case_name
        _copy_case(case, feature_base)

        def mutate_feature(pdf: pikepdf.Pdf, kind: str = mutation) -> None:
            if kind == "annotations":
                del pdf.pages[0].obj["/Annots"]
            elif kind == "form":
                del pdf.Root["/AcroForm"]
            else:
                del pdf.Root["/Outlines"]

        _save_pdf(case / "quarantine" / "derivative.pdf", mutate_feature)
        cases.append((case_name, case, "reject"))

    continuation_source = worksheet_pdf(page_count=1)
    continuation_job = _job(
        continuation_source,
        (
            _appendix_answer("Q1", "First exact continuation answer."),
            _appendix_answer("Q2", "Second exact continuation answer."),
        ),
    )
    continuation_base = root / "continuation_base"
    _write_job(continuation_base, continuation_source, continuation_job)
    _render(continuation_base)

    order = root / "continuation_ordering_error"
    _altered_derivative(
        order,
        continuation_source,
        continuation_job,
        lambda raw: raw["answers"].reverse(),
    )
    cases.append(("continuation_ordering_error", order, "reject"))

    continuation_text = root / "continuation_text_error"

    def alter_continuation(raw: dict[str, Any]) -> None:
        text = "Wrong continuation answer text."
        answer = raw["answers"][0]
        answer["committed_text"] = text
        answer["committed_text_sha256"] = sha256_hex(text.encode())
        answer["continuation"]["paragraphs"] = [text]

    _altered_derivative(
        continuation_text, continuation_source, continuation_job, alter_continuation
    )
    cases.append(("continuation_text_error", continuation_text, "reject"))

    wrong_committed = root / "valid_pdf_wrong_committed_answer"

    def alter_committed(raw: dict[str, Any]) -> None:
        text = "A different reviewed answer that was never committed."
        answer = raw["answers"][0]
        answer["committed_text"] = text
        answer["committed_text_sha256"] = sha256_hex(text.encode())
        answer["lines"][0]["text"] = text

    _altered_derivative(wrong_committed, source, job, alter_committed)
    cases.append(("valid_pdf_wrong_committed_answer", wrong_committed, "reject"))

    untouched = root / "untouched_source_returned"
    _copy_case(untouched, base)
    shutil.copy2(untouched / "source.pdf", untouched / "quarantine" / "derivative.pdf")
    cases.append(("untouched_source_returned", untouched, "reject"))
    return cases


def differential(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name, case_root, expected in _prepare_differential(root):
        validators = {
            validator: _validator(case_root, validator) for validator in ("qpdf", "pdfbox", "pdfjs")
        }
        rows.append(
            {
                "case": name,
                "expected": expected,
                "validators": validators,
                "gate_accepts": {
                    "full": all(item["accepted"] for item in validators.values()),
                    "qpdf_pdfbox": (
                        validators["qpdf"]["accepted"] and validators["pdfbox"]["accepted"]
                    ),
                    "pdfbox_only": validators["pdfbox"]["accepted"],
                },
            }
        )
    qpdf_pdfbox_misses = [
        row["case"]
        for row in rows
        if row["expected"] == "reject"
        and row["validators"]["qpdf"]["accepted"]
        and row["validators"]["pdfbox"]["accepted"]
    ]
    pdfjs_unique = [
        row["case"]
        for row in rows
        if row["case"] in qpdf_pdfbox_misses and not row["validators"]["pdfjs"]["accepted"]
    ]
    return {
        "cases": rows,
        "known_defects_accepted_by_qpdf_plus_pdfbox": qpdf_pdfbox_misses,
        "critical_defects_uniquely_rejected_by_pdfjs": pdfjs_unique,
        "all_gate_variants_match_expected": {
            gate: all(row["gate_accepts"][gate] == (row["expected"] == "accept") for row in rows)
            for gate in ("full", "qpdf_pdfbox", "pdfbox_only")
        },
    }


def _document_job(size: Literal["small", "medium", "large"]) -> tuple[bytes, PdfRenderJob]:
    if size == "small":
        pages, inline_count, appendices = 2, 3, 0
    elif size == "medium":
        pages, inline_count, appendices = 10, 8, 1
    else:
        pages, inline_count, appendices = 50, 30, 3
    source = worksheet_pdf(page_count=pages)
    answers: list[RenderAnswer] = []
    for index in range(inline_count):
        page = index % pages + 1
        first = f"Approved answer {index + 1}: the office keeps exact text,"
        second = "coordinates, and source evidence intact."
        answers.append(
            _multiline_answer(
                f"I{index + 1}",
                first,
                second,
                page_number=page,
                baseline_y_mpt=120_000 + (index // pages) * 36_000,
            )
            if size != "small"
            else _line_answer(
                f"I{index + 1}",
                f"{first} {second}",
                page_number=page,
                baseline_y_mpt=120_000 + (index // pages) * 24_000,
            )
        )
    for index in range(appendices):
        paragraph = (
            f"Continuation {index + 1} preserves the exact committed answer. "
            "It contains several sentences so wrapping, page construction, "
            "and ordering are exercised. "
        ) * (8 if size == "medium" else 70)
        text = (
            paragraph.strip()
            + "\n\n"
            + (
                "A second approved paragraph remains distinct and follows "
                "the first paragraph exactly. "
                * 12
            ).strip()
        )
        answers.append(_appendix_answer(f"A{index + 1}", text, page_number=min(index + 1, pages)))
    return source, _job(source, answers)


def _profile(root: Path, process_ms: int) -> dict[str, Any]:
    raw = json.loads((root / "pdfbox-profile.json").read_text(encoding="utf-8"))
    raw["jvm_process_overhead_ms"] = max(
        0.0, process_ms - float(raw["validator_internal_total_ms"])
    )
    return raw


def _validate_gate(
    root: Path, gate: Gate
) -> tuple[dict[str, int], dict[str, int | None], dict[str, Any]]:
    times: dict[str, int] = {}
    rss: dict[str, int | None] = {}
    if gate in {"full", "qpdf_pdfbox"}:
        result = _validator(root, "qpdf")
        if not result["accepted"]:
            raise RuntimeError("qpdf rejected a valid benchmark derivative")
        times["qpdf_ms"] = result["duration_ms"]
        rss["qpdf_rss_bytes"] = result["peak_rss_bytes"]
    result = _validator(root, "pdfbox")
    if not result["accepted"]:
        raise RuntimeError(f"PDFBox rejected a valid benchmark derivative: {result['code']}")
    times["pdfbox_ms"] = result["duration_ms"]
    rss["pdfbox_rss_bytes"] = result["peak_rss_bytes"]
    profile = _profile(root, result["duration_ms"])
    if gate == "full":
        result = _validator(root, "pdfjs")
        if not result["accepted"]:
            raise RuntimeError("PDF.js rejected a valid benchmark derivative")
        times["pdfjs_ms"] = result["duration_ms"]
        rss["pdfjs_parent_rss_bytes"] = result["peak_rss_bytes"]
    return times, rss, profile


def _one_benchmark(root: Path, source: bytes, job: PdfRenderJob, gate: Gate) -> dict[str, Any]:
    started = time.perf_counter()
    _write_job(root, source, job)
    worker = _render(root)
    status = WorkerSuccess.model_validate_json((root / "worker-status.json").read_bytes())
    times, rss, profile = _validate_gate(root, gate)
    output_bytes = (root / "quarantine" / "derivative.pdf").stat().st_size
    temporary_bytes = sum(item.stat().st_size for item in root.rglob("*") if item.is_file())
    before_cleanup = time.perf_counter()
    shutil.rmtree(root)
    cleanup_ms = round((time.perf_counter() - before_cleanup) * 1000)
    row: dict[str, Any] = {
        "total_ms": round((time.perf_counter() - started) * 1000),
        "openpdf_process_ms": worker.duration_ms,
        "openpdf_internal_render_ms": status.render_millis,
        "validation_ms": sum(times.values()),
        "source_pages": status.source_pages,
        "continuation_pages": status.continuation_pages,
        "output_pages": status.output_pages,
        "answers": len(job.answers),
        "output_bytes": output_bytes,
        "temporary_bytes": temporary_bytes,
        "cleanup_ms": cleanup_ms,
        "openpdf_rss_bytes": worker.peak_rss_bytes,
        "pdfbox_profile": profile,
        **times,
        **rss,
    }
    return row


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    numeric = sorted(key for key in rows[0] if all(isinstance(row.get(key), int) for row in rows))
    result: dict[str, Any] = {"jobs": len(rows), "metrics": {}}
    for key in numeric:
        values = sorted(int(row[key]) for row in rows)
        result["metrics"][key] = {
            "mean": round(statistics.mean(values)),
            "p50": round(statistics.median(values)),
            "p95": values[max(0, math.ceil(0.95 * len(values)) - 1)],
            "max": values[-1],
        }
    phases = sorted(rows[0]["pdfbox_profile"]["phases_ms"])
    result["pdfbox_profile_mean_ms"] = {
        phase: round(
            statistics.mean(float(row["pdfbox_profile"]["phases_ms"][phase]) for row in rows), 3
        )
        for phase in phases
    }
    result["pdfbox_profile_mean_ms"]["validator_internal_total_ms"] = round(
        statistics.mean(
            float(row["pdfbox_profile"]["validator_internal_total_ms"]) for row in rows
        ),
        3,
    )
    result["pdfbox_profile_mean_ms"]["jvm_process_overhead_ms"] = round(
        statistics.mean(float(row["pdfbox_profile"]["jvm_process_overhead_ms"]) for row in rows),
        3,
    )
    return result


def benchmarks(root: Path) -> dict[str, Any]:
    source, job = _document_job("small")
    variants: dict[str, Any] = {}
    for gate in ("full", "qpdf_pdfbox", "pdfbox_only"):
        rows = [_one_benchmark(root / f"{gate}-{index}", source, job, gate) for index in range(10)]
        variants[gate] = {"summary": summarize(rows), "runs": rows}
    return variants


def size_benchmarks(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for size in ("small", "medium", "large"):
        source, job = _document_job(size)
        rows = [
            _one_benchmark(root / f"{size}-{index}", source, job, "qpdf_pdfbox")
            for index in range(3)
        ]
        result[size] = {
            "source_pages": job.source.page_count,
            "answers": len(job.answers),
            "appendix_answers": sum(
                answer.placement_classification == "appendix" for answer in job.answers
            ),
            "source_bytes": len(source),
            "summary": summarize(rows),
            "runs": rows,
        }
    return result


def _preflight() -> None:
    required = (JAR, FONT, PDFJS, QPDF, JAVA, NODE)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"required preserved spike artifacts are missing: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=EXPERIMENT / "evidence.json")
    parser.add_argument(
        "--section", choices=("all", "differential", "benchmarks", "sizes"), default="all"
    )
    args = parser.parse_args()
    _preflight()
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "java": subprocess.check_output(  # noqa: S603
                [str(JAVA), "-version"], stderr=subprocess.STDOUT
            )
            .decode(errors="replace")
            .splitlines()[0],
            "node": subprocess.check_output(  # noqa: S603
                [str(NODE), "--version"]
            )
            .decode()
            .strip(),
            "qpdf": subprocess.check_output(  # noqa: S603
                [str(QPDF), "--version"]
            )
            .decode()
            .splitlines()[0],
            "note": "Developer-workstation sequential evidence; not a throughput claim.",
            "memory_note": (
                "RSS samples cover each launched parent process; "
                "Chromium child RSS is not included."
            ),
        },
        "baseline": json.loads((INTEGRATION / "benchmark-output.json").read_text(encoding="utf-8")),
    }
    with tempfile.TemporaryDirectory(prefix="claros-openpdf-validation-") as temporary:
        temporary_root = Path(temporary)
        if args.section in {"all", "differential"}:
            evidence["differential"] = differential(temporary_root / "differential")
        if args.section in {"all", "benchmarks"}:
            evidence["validation_variants"] = benchmarks(temporary_root / "benchmarks")
        if args.section in {"all", "sizes"}:
            evidence["document_sizes"] = size_benchmarks(temporary_root / "sizes")
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
