from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.document import (
    ConfirmedAnswerForExport,
    DocumentEngineError,
    QuestionEvidence,
    extract_physical_ir,
    resolve_placement,
)
from backend.document_execution import DocumentProcessExecutor
from backend.openpdf import (
    OpenPdfConfigurationError,
    OpenPdfRuntime,
    OpenPdfWorkerExportEngine,
)
from backend.service import build_assignment_service
from backend.tests.document.factories import worksheet_pdf


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "storage_backend": "local",
        "local_storage_path": tmp_path / "objects",
    }
    values.update(overrides)
    return Settings(**values)


def _answer(text: str = "office official efficient file first affinity different"):
    source = worksheet_pdf()
    physical_ir = extract_physical_ir(source)
    prompt = next(
        block
        for block in physical_ir.pages[0].blocks
        if block.kind == "text" and block.text and block.text.endswith("?")
    )
    evidence = QuestionEvidence("question-test-1", "Question 1", (prompt.id,))
    plan = resolve_placement(physical_ir, evidence, text)
    return (
        source,
        physical_ir,
        ConfirmedAnswerForExport(
            evidence.question_id,
            evidence.display_identifier,
            evidence.prompt_block_ids,
            (),
            text,
            plan.placement_hash,
        ),
    )


def test_current_engine_remains_the_default_without_openpdf_fallback(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        openpdf_jar_path=tmp_path / "missing.jar",
        openpdf_qpdf_path=tmp_path / "missing-qpdf",
        openpdf_java_command="missing-java",
    )

    service = build_assignment_service(settings)

    assert settings.pdf_engine == "current"
    assert isinstance(service.document_executor, DocumentProcessExecutor)


def test_application_factory_selects_the_real_openpdf_engine(
    tmp_path: Path,
    openpdf_worker_jar: Path,
    qpdf_executable: Path,
) -> None:
    service = build_assignment_service(
        _settings(
            tmp_path,
            pdf_engine="openpdf",
            openpdf_jar_path=openpdf_worker_jar,
            openpdf_qpdf_path=qpdf_executable,
        )
    )

    assert isinstance(service.document_executor, OpenPdfWorkerExportEngine)
    assert service.document_executor.engine_name == "openpdf"


def test_pdf_engine_setting_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", pdf_engine="automatic")


@pytest.mark.parametrize(
    ("override", "message"),
    (
        ({"openpdf_jar_path": "missing.jar"}, "worker artifact"),
        ({"openpdf_qpdf_path": "missing-qpdf"}, "qpdf executable"),
        ({"openpdf_java_command": "missing-java-command"}, "Java 21"),
        ({"openpdf_font_root": "missing-fonts"}, "approved PDF font"),
    ),
)
def test_openpdf_selection_fails_startup_with_clear_dependency_diagnostics(
    tmp_path: Path,
    openpdf_worker_jar: Path,
    qpdf_executable: Path,
    override: dict[str, str],
    message: str,
) -> None:
    values: dict[str, object] = {
        "pdf_engine": "openpdf",
        "openpdf_jar_path": openpdf_worker_jar,
        "openpdf_qpdf_path": qpdf_executable,
    }
    values.update(
        {
            key: tmp_path / value if "command" not in key else value
            for key, value in override.items()
        }
    )

    with pytest.raises(OpenPdfConfigurationError, match=message):
        build_assignment_service(_settings(tmp_path, **values))


@pytest.mark.anyio
async def test_source_placement_and_unsupported_input_fail_closed_before_worker_launch(
    tmp_path: Path,
) -> None:
    source, physical_ir, answer = _answer()
    engine = OpenPdfWorkerExportEngine(runtime=OpenPdfRuntime(work_root=tmp_path))
    cases = (
        (source + b"\n", physical_ir, answer, "stale_source"),
        (
            source,
            physical_ir,
            replace(answer, reviewed_placement_hash="0" * 64),
            "placement_changed",
        ),
        (source, physical_ir, replace(answer, exact_text="مرحبا"), "unsupported_rtl"),
        (source, physical_ir, replace(answer, exact_text="😀"), "unsupported_glyph"),
    )

    for source_value, ir_value, answer_value, code in cases:
        with pytest.raises(DocumentEngineError) as raised:
            await engine.export(
                source_value,
                ir_value,
                "Worksheet",
                (answer_value,),
                timeout_seconds=5,
            )
        assert raised.value.code == code
