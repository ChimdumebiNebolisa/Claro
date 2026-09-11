# ruff: noqa: RUF001, S101, S607

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pikepdf
import pytest
from openpdf_integration.adapter import (
    OpenPdfWorkerExportEngine,
    SpikeRuntime,
    _build_job,
    _revalidate_plans,
    select_pdf_engine,
)
from openpdf_integration.contract import PdfRenderJob
from pydantic import ValidationError
from pypdf import PdfReader

from backend.document import (
    ConfirmedAnswerForExport,
    DocumentEngineError,
    QuestionEvidence,
    extract_physical_ir,
    resolve_placement,
)
from backend.document.models import sha256_hex
from backend.document_execution import DocumentExecutionFailure, DocumentExecutionTimeout
from backend.tests.document.factories import worksheet_pdf

ROOT = Path(__file__).resolve().parents[1]
FAKE_WORKER = ROOT / "tests" / "helpers" / "fake_worker.py"


def _case(text: str = "office official efficient file first affinity different"):
    source = worksheet_pdf()
    physical_ir = extract_physical_ir(source)
    prompt = next(
        block
        for block in physical_ir.pages[0].blocks
        if block.kind == "text" and block.text and block.text.endswith("?")
    )
    question = QuestionEvidence(
        question_id="question-test-1",
        display_identifier="Question 1",
        prompt_block_ids=(prompt.id,),
    )
    plan = resolve_placement(physical_ir, question, text)
    answer = ConfirmedAnswerForExport(
        question_id=question.question_id,
        display_identifier=question.display_identifier,
        prompt_block_ids=question.prompt_block_ids,
        context_block_ids=(),
        exact_text=text,
        reviewed_placement_hash=plan.placement_hash,
    )
    return source, physical_ir, answer, plan


def _runtime(tmp_path: Path, **changes: object) -> SpikeRuntime:
    values = {"work_root": tmp_path}
    values.update(changes)
    return SpikeRuntime(**values)  # type: ignore[arg-type]


def _fake_runtime(tmp_path: Path, mode: str, **changes: object) -> SpikeRuntime:
    return _runtime(
        tmp_path,
        worker_command_override=(sys.executable, str(FAKE_WORKER), mode),
        **changes,
    )


def _contract(source: bytes, physical_ir, answer) -> PdfRenderJob:
    return _build_job(
        source,
        physical_ir,
        "Worksheet",
        _revalidate_plans(physical_ir, (answer,)),
        max_input_bytes=10 * 1024 * 1024,
        max_output_bytes=64 * 1024 * 1024,
        max_pages=8,
        font_sha256="b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5",
    )


def test_contract_is_canonical_strict_and_contains_no_ambient_authority() -> None:
    source, physical_ir, answer, _plan = _case()
    contract = _contract(source, physical_ir, answer)
    payload = contract.canonical_bytes()
    assert PdfRenderJob.from_bytes(payload) == contract
    serialized = json.loads(payload)
    assert not any(
        key in json.dumps(serialized)
        for key in ("font_path", "file_path", "url", "html", "shell", "credentials")
    )

    serialized["source_path"] = "C:/attacker/source.pdf"
    with pytest.raises(ValidationError):
        PdfRenderJob.model_validate(serialized, strict=True)

    noncanonical = json.dumps(contract.model_dump(mode="json"), ensure_ascii=False).encode()
    with pytest.raises(ValueError, match="not canonical"):
        PdfRenderJob.from_bytes(noncanonical)


def test_engine_flag_defaults_to_control_and_cannot_enable_spike_in_production(
    tmp_path: Path,
) -> None:
    control = object()
    assert select_pdf_engine(control, environment="test", environ={}) is control  # type: ignore[arg-type]
    selected = select_pdf_engine(
        control,  # type: ignore[arg-type]
        environment="test",
        runtime=_runtime(tmp_path),
        environ={"CLAROS_PDF_ENGINE": "openpdf-spike"},
    )
    assert isinstance(selected, OpenPdfWorkerExportEngine)
    with pytest.raises(ValueError, match="not authorized"):
        select_pdf_engine(
            control,  # type: ignore[arg-type]
            environment="production",
            runtime=_runtime(tmp_path),
            environ={"CLAROS_PDF_ENGINE": "openpdf-spike"},
        )


@pytest.mark.anyio
async def test_real_worker_fixes_ligatures_and_passes_all_release_validators(
    tmp_path: Path,
) -> None:
    source, physical_ir, answer, plan = _case()
    source_before = bytes(source)
    engine = OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path))

    artifact = await engine.export(
        source, physical_ir, "Worksheet", (answer,), timeout_seconds=45
    )

    assert source == source_before
    assert sha256_hex(source) == physical_ir.source_sha256
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(artifact.pdf_bytes)).pages
    )
    assert answer.exact_text in extracted
    assert "ofce ofcial efcient" not in extracted
    manifest = json.loads(artifact.manifest_bytes)
    assert manifest["answers"][0]["placement_hash"] == plan.placement_hash
    assert manifest["answers"][0]["exact_text_sha256"] == sha256_hex(
        answer.exact_text.encode()
    )
    assert [item.label for item in engine.last_evidence.processes] == [
        "openpdf",
        "qpdf",
        "pdfbox",
        "pdfjs",
    ]
    assert engine.last_evidence.output_bytes == len(artifact.pdf_bytes)
    assert engine.last_evidence.peak_worker_rss_bytes is not None
    assert engine.last_job_path is not None and not engine.last_job_path.exists()


@pytest.mark.anyio
async def test_continuation_layout_crosses_pages_and_is_independently_validated(
    tmp_path: Path,
) -> None:
    text = (
        "The office is efficient, accurate, and preserved (exactly) with é, ñ, ü, α, and Γ. "
        * 95
    ).strip()
    source, physical_ir, answer, plan = _case(text)
    assert plan.outcome == "appendix"
    engine = OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path))

    artifact = await engine.export(
        source, physical_ir, "Biology worksheet", (answer,), timeout_seconds=60
    )

    manifest = json.loads(artifact.manifest_bytes)
    assert manifest["appendix_page_count"] >= 2
    reader = PdfReader(BytesIO(artifact.pdf_bytes))
    assert len(reader.pages) == 1 + manifest["appendix_page_count"]
    appendix = "\n".join(page.extract_text() or "" for page in reader.pages[1:])
    assert "Question 1" in appendix
    assert "Attached answer page 1" in appendix
    assert "The office is efficient" in appendix
    assert "α, and Γ" in appendix


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("mode", "timeout", "error_type", "error_code"),
    (
        ("crash", 5.0, DocumentExecutionFailure, None),
        ("timeout", 0.15, DocumentExecutionTimeout, None),
        ("malformed", 5.0, DocumentExecutionFailure, None),
        ("invalid-pdf", 5.0, DocumentEngineError, "invalid_export"),
        ("copy-source", 15.0, DocumentEngineError, "invalid_export"),
        ("wrong-text", 20.0, DocumentEngineError, "invalid_export"),
        ("wrong-coordinate", 20.0, DocumentEngineError, "invalid_export"),
        ("mutate-contract", 5.0, DocumentExecutionFailure, None),
        ("oversize", 5.0, DocumentEngineError, "invalid_export"),
    ),
)
async def test_process_and_validation_failures_never_release_quarantine(
    tmp_path: Path,
    mode: str,
    timeout: float,
    error_type: type[BaseException],
    error_code: str | None,
) -> None:
    source, physical_ir, answer, _plan = _case()
    changes = {"max_output_bytes": 2_048} if mode == "oversize" else {}
    engine = OpenPdfWorkerExportEngine(runtime=_fake_runtime(tmp_path, mode, **changes))

    with pytest.raises(error_type) as raised:
        await engine.export(
            source, physical_ir, "Worksheet", (answer,), timeout_seconds=timeout
        )
    if error_code is not None:
        assert isinstance(raised.value, DocumentEngineError)
        assert raised.value.code == error_code
    assert engine.active_process_count == 0
    assert engine.last_job_path is not None and not engine.last_job_path.exists()


@pytest.mark.anyio
async def test_source_placement_rtl_size_page_and_font_fail_closed_before_release(
    tmp_path: Path,
) -> None:
    source, physical_ir, answer, _plan = _case()

    cases = [
        (
            OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path / "input", max_input_bytes=10)),
            source,
            physical_ir,
            answer,
            "file_too_large",
        ),
        (
            OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path / "source")),
            source + b"\n",
            physical_ir,
            answer,
            "stale_source",
        ),
        (
            OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path / "placement")),
            source,
            physical_ir,
            replace(answer, reviewed_placement_hash="0" * 64),
            "placement_changed",
        ),
        (
            OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path / "evidence")),
            source,
            replace(physical_ir, normalization_sha256="0" * 64),
            answer,
            "placement_changed",
        ),
        (
            OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path / "rtl")),
            source,
            physical_ir,
            replace(answer, exact_text="مرحبا"),
            "unsupported_rtl",
        ),
        (
            OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path / "font", font_root=tmp_path)),
            source,
            physical_ir,
            answer,
            "font_not_allowlisted",
        ),
    ]
    for work in (
        tmp_path / "input",
        tmp_path / "source",
        tmp_path / "placement",
        tmp_path / "evidence",
        tmp_path / "rtl",
    ):
        work.mkdir()
    for engine, source_value, ir_value, answer_value, code in cases:
        with pytest.raises(DocumentEngineError) as raised:
            await engine.export(
                source_value,
                ir_value,
                "Worksheet",
                (answer_value,),
                timeout_seconds=10,
            )
        assert raised.value.code == code

    multi_source = worksheet_pdf(page_count=2)
    multi_ir = extract_physical_ir(multi_source)
    limited = OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path / "pages", max_pages=1))
    (tmp_path / "pages").mkdir()
    with pytest.raises(DocumentEngineError) as raised:
        await limited.export(multi_source, multi_ir, "Worksheet", (answer,), timeout_seconds=10)
    assert raised.value.code == "page_limit_exceeded"


@pytest.mark.anyio
async def test_real_worker_classifies_rebuilt_xref_and_output_bound(tmp_path: Path) -> None:
    source, _ir, _answer, _plan = _case()
    malformed = re.sub(
        br"startxref\s+\d+\s+%%EOF",
        b"startxref\n0\n%%EOF",
        source,
        count=1,
    )
    malformed_ir = extract_physical_ir(malformed)
    prompt = next(
        block
        for block in malformed_ir.pages[0].blocks
        if block.kind == "text" and block.text and block.text.endswith("?")
    )
    question = QuestionEvidence("question-rebuilt-1", "Question 1", (prompt.id,))
    plan = resolve_placement(malformed_ir, question, "A reviewed answer.")
    answer = ConfirmedAnswerForExport(
        question.question_id,
        question.display_identifier,
        question.prompt_block_ids,
        (),
        "A reviewed answer.",
        plan.placement_hash,
    )
    rebuilt_root = tmp_path / "rebuilt"
    rebuilt_root.mkdir()
    rebuilt = OpenPdfWorkerExportEngine(runtime=_runtime(rebuilt_root))
    with pytest.raises(DocumentEngineError) as raised:
        await rebuilt.export(
            malformed, malformed_ir, "Worksheet", (answer,), timeout_seconds=20
        )
    assert raised.value.code == "unsupported_rebuilt_xref"

    source, ir, answer, _plan = _case()
    output_root = tmp_path / "output"
    output_root.mkdir()
    bounded = OpenPdfWorkerExportEngine(
        runtime=_runtime(output_root, max_output_bytes=len(source) + 50)
    )
    with pytest.raises(DocumentEngineError) as raised:
        await bounded.export(source, ir, "Worksheet", (answer,), timeout_seconds=20)
    assert raised.value.code == "resource_limit"


@pytest.mark.anyio
async def test_bounded_compressed_object_stream_input_passes_the_gate(tmp_path: Path) -> None:
    ordinary, _ir, _answer, _plan = _case()
    output = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(ordinary)) as pdf:
        pdf.save(
            output,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            deterministic_id=True,
        )
    source = output.getvalue()
    physical_ir = extract_physical_ir(source)
    prompt = next(
        block
        for block in physical_ir.pages[0].blocks
        if block.kind == "text" and block.text and block.text.endswith("?")
    )
    question = QuestionEvidence("question-compressed-1", "Question 1", (prompt.id,))
    text = "Compressed office content still validates exactly."
    plan = resolve_placement(physical_ir, question, text)
    answer = ConfirmedAnswerForExport(
        question.question_id,
        question.display_identifier,
        question.prompt_block_ids,
        (),
        text,
        plan.placement_hash,
    )
    engine = OpenPdfWorkerExportEngine(runtime=_runtime(tmp_path))

    artifact = await engine.export(
        source, physical_ir, "Compressed worksheet", (answer,), timeout_seconds=45
    )

    assert artifact.pdf_bytes.startswith(b"%PDF-")
    assert engine.last_evidence.output_bytes <= engine._runtime.max_output_bytes


def test_jvm_heap_limit_terminates_bounded_overallocation() -> None:
    jar = ROOT / "target" / "openpdf-integration-0.1.0-SNAPSHOT-all.jar"
    result = subprocess.run(  # noqa: S603
        [
            "java",
            "-Xms16m",
            "-Xmx32m",
            "-cp",
            str(jar),
            "org.claros.openpdfintegration.ResourceProbeMain",
            "allocate-96-mib",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
