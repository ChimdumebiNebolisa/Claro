"""Experimental Claros adapter: OpenPDF render, quarantine, independent release gate."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from anyio.to_thread import run_sync as run_sync_in_thread
from pydantic import ValidationError

from backend.document import ConfirmedAnswerForExport, DocumentEngineError, resolve_placement
from backend.document.errors import document_error
from backend.document.exporter import DocumentExportManifest, ExportAnswerManifest
from backend.document.geometry import PlacementPlan
from backend.document.models import PhysicalDocumentIR, sha256_hex
from backend.document_execution import (
    DocumentExecutionFailure,
    DocumentExecutionTimeout,
    DocumentProcessExecutor,
    RenderedExport,
)

from .contract import (
    ContinuationInstruction,
    GeneratedLine,
    PageGeometry,
    PdfRenderJob,
    RenderAnswer,
    ResourceLimits,
    SourceBinding,
    ValidatorSuccess,
    WorkerSuccess,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_JAR = _EXPERIMENT_ROOT / "target" / "openpdf-integration-0.1.0-SNAPSHOT-all.jar"
_DEFAULT_FONT_ROOT = _REPO_ROOT / "assets" / "fonts" / "noto-sans"
_FONT_SHA256 = "b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5"
_MAX_STATUS_BYTES = 16 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_SAFE_WORKER_CODES = {
    "invalid_contract",
    "stale_source",
    "stale_physical_ir",
    "placement_changed",
    "unsupported_rtl",
    "unsupported_rebuilt_xref",
    "font_not_allowlisted",
    "unsupported_glyph",
    "resource_limit",
    "invalid_pdf",
}
_RTL_BIDI = {"R", "AL", "AN"}


class ExportEngine(Protocol):
    async def analyze(self, *args: Any, **kwargs: Any) -> Any: ...

    async def export(
        self,
        source_pdf: bytes,
        physical_ir: PhysicalDocumentIR,
        worksheet_title: str,
        answers: tuple[ConfirmedAnswerForExport, ...],
        *,
        timeout_seconds: float,
    ) -> RenderedExport: ...


@dataclass(frozen=True, slots=True)
class SpikeRuntime:
    """Server-owned process and resource policy; no field is supplied by an export caller."""

    jar_path: Path = _DEFAULT_JAR
    font_root: Path = _DEFAULT_FONT_ROOT
    qpdf_path: Path | None = None
    java_command: str = "java"
    node_command: str = "node"
    max_input_bytes: int = 10 * 1024 * 1024
    max_output_bytes: int = 64 * 1024 * 1024
    max_pages: int = 8
    jvm_heap_mib: int = 192
    work_root: Path | None = None
    worker_command_override: tuple[str, ...] | None = None
    pdfbox_command_override: tuple[str, ...] | None = None
    pdfjs_command_override: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if min(
            self.max_input_bytes,
            self.max_output_bytes,
            self.max_pages,
            self.jvm_heap_mib,
        ) <= 0:
            raise ValueError("OpenPDF spike limits must be positive")
        if self.jvm_heap_mib > 1_024:
            raise ValueError("OpenPDF spike heap must remain bounded")


@dataclass(frozen=True, slots=True)
class ProcessEvidence:
    label: str
    duration_ms: int
    peak_rss_bytes: int | None
    return_code: int


@dataclass(slots=True)
class ExportEvidence:
    job_id: str = ""
    source_bytes: int = 0
    output_bytes: int = 0
    temporary_peak_bytes: int = 0
    cleanup_ms: int = 0
    worker_internal_render_ms: int = 0
    processes: list[ProcessEvidence] = field(default_factory=list)

    @property
    def render_ms(self) -> int:
        return sum(item.duration_ms for item in self.processes if item.label == "openpdf")

    @property
    def validation_ms(self) -> int:
        return sum(item.duration_ms for item in self.processes if item.label != "openpdf")

    @property
    def total_process_ms(self) -> int:
        return sum(item.duration_ms for item in self.processes)

    @property
    def peak_worker_rss_bytes(self) -> int | None:
        values = [
            item.peak_rss_bytes
            for item in self.processes
            if item.label == "openpdf" and item.peak_rss_bytes is not None
        ]
        return max(values) if values else None


class OpenPdfWorkerExportEngine:
    """Use OpenPDF only behind a process boundary and all-or-nothing validation gate."""

    def __init__(
        self,
        *,
        control_engine: ExportEngine | None = None,
        runtime: SpikeRuntime | None = None,
    ) -> None:
        self._control = control_engine or DocumentProcessExecutor()
        self._runtime = runtime or SpikeRuntime()
        self._lock = threading.Lock()
        self._active: dict[int, subprocess.Popen[bytes]] = {}
        self.last_evidence = ExportEvidence()
        self.last_job_path: Path | None = None

    @property
    def active_process_count(self) -> int:
        with self._lock:
            return len(self._active)

    async def analyze(self, *args: Any, **kwargs: Any) -> Any:
        return await self._control.analyze(*args, **kwargs)

    async def export(
        self,
        source_pdf: bytes,
        physical_ir: PhysicalDocumentIR,
        worksheet_title: str,
        answers: tuple[ConfirmedAnswerForExport, ...],
        *,
        timeout_seconds: float,
    ) -> RenderedExport:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        started = time.monotonic()
        deadline = started + timeout_seconds
        evidence = ExportEvidence(source_bytes=len(source_pdf))
        self.last_evidence = evidence
        if len(source_pdf) > self._runtime.max_input_bytes:
            raise document_error("file_too_large")
        if not hmac.compare_digest(sha256_hex(source_pdf), physical_ir.source_sha256):
            raise document_error("stale_source")
        if len(physical_ir.pages) > self._runtime.max_pages:
            raise document_error("page_limit_exceeded")
        planned = _revalidate_plans(physical_ir, answers)
        job = _build_job(
            source_pdf,
            physical_ir,
            worksheet_title,
            planned,
            max_input_bytes=self._runtime.max_input_bytes,
            max_output_bytes=self._runtime.max_output_bytes,
            max_pages=self._runtime.max_pages,
            font_sha256=self._font_sha256(),
        )
        # Serialize and parse again before crossing the process boundary.
        contract_bytes = job.canonical_bytes()
        job = PdfRenderJob.from_bytes(contract_bytes)
        evidence.job_id = job.job_id
        job_root = Path(
            tempfile.mkdtemp(
                prefix="claros-openpdf-",
                dir=str(self._runtime.work_root) if self._runtime.work_root else None,
            )
        ).resolve()
        self.last_job_path = job_root
        try:
            await run_sync_in_thread(
                _write_inputs,
                job_root,
                source_pdf,
                contract_bytes,
                abandon_on_cancel=True,
            )
            worker = await self._run(
                "openpdf", self._worker_command(job_root), job_root, deadline, evidence
            )
            if worker.return_code != 0:
                raise DocumentExecutionFailure("OpenPDF worker exited unexpectedly")
            if not hmac.compare_digest(
                _digest_path(job_root / "job.json"), sha256_hex(contract_bytes)
            ):
                raise DocumentExecutionFailure("OpenPDF worker changed its authority contract")
            status = _read_worker_status(job_root)
            if isinstance(status, DocumentEngineError):
                raise status
            if status.job_id != job.job_id or status.source_sha256 != job.source.sha256:
                raise DocumentExecutionFailure("OpenPDF worker response binding is invalid")
            evidence.worker_internal_render_ms = status.render_millis
            derivative = job_root / "quarantine" / "derivative.pdf"
            _verify_quarantine_file(derivative, status, self._runtime.max_output_bytes)
            await self._validate(job_root, job, status, deadline, evidence)
            # Recheck every binding after validation and immediately before release.
            if not hmac.compare_digest(
                _digest_path(job_root / "job.json"), sha256_hex(contract_bytes)
            ):
                raise document_error("invalid_export")
            if not hmac.compare_digest(_digest_path(job_root / "source.pdf"), job.source.sha256):
                raise document_error("stale_source")
            if not hmac.compare_digest(_digest_path(derivative), status.output_sha256):
                raise document_error("invalid_export")
            pdf_bytes = _read_bounded(derivative, self._runtime.max_output_bytes)
            evidence.output_bytes = len(pdf_bytes)
            evidence.temporary_peak_bytes = _tree_size(job_root)
            manifest = _manifest(
                job,
                planned,
                worksheet_title,
                output_sha256=status.output_sha256,
                continuation_pages=status.continuation_pages,
            ).canonical_bytes()
            if len(manifest) > _MAX_MANIFEST_BYTES:
                raise document_error("invalid_export")
            return RenderedExport(pdf_bytes=pdf_bytes, manifest_bytes=manifest)
        except BaseException:
            shutil.rmtree(job_root / "quarantine", ignore_errors=True)
            raise
        finally:
            cleanup_started = time.monotonic()
            await run_sync_in_thread(_cleanup_job, job_root, abandon_on_cancel=True)
            evidence.cleanup_ms = round((time.monotonic() - cleanup_started) * 1000)

    async def _validate(
        self,
        job_root: Path,
        job: PdfRenderJob,
        worker: WorkerSuccess,
        deadline: float,
        evidence: ExportEvidence,
    ) -> None:
        qpdf = self._qpdf_path()
        result = await self._run(
            "qpdf",
            (str(qpdf), "--check", str(job_root / "quarantine" / "derivative.pdf")),
            job_root,
            deadline,
            evidence,
        )
        if result.return_code != 0:
            raise document_error("invalid_export")
        pdfbox = await self._run(
            "pdfbox", self._pdfbox_command(job_root), job_root, deadline, evidence
        )
        if pdfbox.return_code != 0:
            raise document_error("invalid_export")
        pdfbox_status = _read_validator_status(job_root / "pdfbox-status.json", "pdfbox")
        pdfjs = await self._run(
            "pdfjs", self._pdfjs_command(job_root), job_root, deadline, evidence
        )
        if pdfjs.return_code != 0:
            raise document_error("invalid_export")
        pdfjs_status = _read_validator_status(job_root / "pdfjs-status.json", "pdfjs")
        for status in (pdfbox_status, pdfjs_status):
            if status.job_id != job.job_id or status.page_count != worker.output_pages:
                raise document_error("invalid_export")
        if not pdfbox_status.placement_exact or not pdfbox_status.source_preserved:
            raise document_error("invalid_export")
        if pdfjs_status.rendered_pages != worker.output_pages:
            raise document_error("invalid_export")

    async def _run(
        self,
        label: str,
        command: tuple[str, ...],
        cwd: Path,
        deadline: float,
        evidence: ExportEvidence,
    ) -> ProcessEvidence:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DocumentExecutionTimeout("OpenPDF spike exceeded its deadline")
        result = await run_sync_in_thread(
            self._run_blocking,
            label,
            command,
            cwd,
            remaining,
            abandon_on_cancel=True,
        )
        evidence.processes.append(result)
        return result

    def _run_blocking(
        self, label: str, command: tuple[str, ...], cwd: Path, timeout_seconds: float
    ) -> ProcessEvidence:
        kwargs: dict[str, Any] = {
            "cwd": str(_REPO_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
            "env": _safe_environment(cwd),
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        started = time.monotonic()
        process = subprocess.Popen(list(command), **kwargs)  # noqa: S603
        with self._lock:
            self._active[process.pid] = process
        peak_rss: int | None = None
        try:
            deadline = started + timeout_seconds
            while process.poll() is None:
                peak_rss = _max_optional(peak_rss, _process_rss(process.pid))
                if time.monotonic() >= deadline:
                    _kill_process(process)
                    raise DocumentExecutionTimeout("OpenPDF spike process exceeded its deadline")
                time.sleep(0.01)
            peak_rss = _max_optional(peak_rss, _process_rss(process.pid))
            return ProcessEvidence(
                label=label,
                duration_ms=round((time.monotonic() - started) * 1000),
                peak_rss_bytes=peak_rss,
                return_code=cast(int, process.returncode),
            )
        finally:
            if process.poll() is None:
                _kill_process(process)
            process.wait()
            with self._lock:
                self._active.pop(process.pid, None)

    def _worker_command(self, job_root: Path) -> tuple[str, ...]:
        if self._runtime.worker_command_override is not None:
            return (*self._runtime.worker_command_override, str(job_root))
        return (
            self._runtime.java_command,
            "-Djava.awt.headless=true",
            f"-Djava.io.tmpdir={job_root / 'tmp'}",
            "-Xms16m",
            f"-Xmx{self._runtime.jvm_heap_mib}m",
            "-jar",
            str(self._runtime.jar_path),
            "--job-dir",
            str(job_root),
            "--font-dir",
            str(self._runtime.font_root),
        )

    def _pdfbox_command(self, job_root: Path) -> tuple[str, ...]:
        if self._runtime.pdfbox_command_override is not None:
            return (*self._runtime.pdfbox_command_override, str(job_root))
        return (
            self._runtime.java_command,
            "-Djava.awt.headless=true",
            f"-Djava.io.tmpdir={job_root / 'tmp'}",
            "-Xms16m",
            f"-Xmx{self._runtime.jvm_heap_mib}m",
            "-cp",
            str(self._runtime.jar_path),
            "org.claros.openpdfintegration.PdfBoxValidatorMain",
            "--job-dir",
            str(job_root),
        )

    def _pdfjs_command(self, job_root: Path) -> tuple[str, ...]:
        if self._runtime.pdfjs_command_override is not None:
            return (*self._runtime.pdfjs_command_override, str(job_root))
        return (
            self._runtime.node_command,
            str(_EXPERIMENT_ROOT / "scripts" / "validate-pdfjs.mjs"),
            str(job_root),
        )

    def _qpdf_path(self) -> Path:
        configured = self._runtime.qpdf_path
        if configured is not None and configured.is_file():
            return configured.resolve()
        found = shutil.which("qpdf")
        if found:
            return Path(found).resolve()
        bundled = _REPO_ROOT / "experiments" / "openpdf-hostile" / ".tools" / "qpdf" / "bin"
        candidate = bundled / ("qpdf.exe" if os.name == "nt" else "qpdf")
        if candidate.is_file():
            return candidate.resolve()
        raise DocumentExecutionFailure("qpdf validator is unavailable")

    def _font_sha256(self) -> str:
        font = self._runtime.font_root / "NotoSans-Regular.ttf"
        if not font.is_file() or font.is_symlink():
            raise DocumentEngineError(
                "font_not_allowlisted", "The approved PDF font is unavailable.", recoverable=True
            )
        actual = _digest_path(font)
        if actual != _FONT_SHA256:
            raise DocumentEngineError(
                "font_not_allowlisted", "The approved PDF font is unavailable.", recoverable=True
            )
        return actual


def select_pdf_engine(
    current: ExportEngine,
    *,
    environment: str,
    runtime: SpikeRuntime | None = None,
    environ: Mapping[str, str] | None = None,
) -> ExportEngine:
    """Experimental-only selection; current remains the unconditional default."""

    value = (environ or os.environ).get("CLAROS_PDF_ENGINE", "current")
    if value == "current":
        return current
    if value != "openpdf-spike":
        raise ValueError("CLAROS_PDF_ENGINE must be current or openpdf-spike")
    if environment == "production":
        raise ValueError("openpdf-spike is not authorized in production")
    return OpenPdfWorkerExportEngine(control_engine=current, runtime=runtime)


def _revalidate_plans(
    physical_ir: PhysicalDocumentIR,
    answers: Sequence[ConfirmedAnswerForExport],
) -> tuple[tuple[ConfirmedAnswerForExport, PlacementPlan, str, int], ...]:
    if not answers:
        raise document_error("no_confirmed_answers")
    question_ids = [answer.question_id for answer in answers]
    if len(question_ids) != len(set(question_ids)):
        raise document_error("invalid_export")
    ordered = sorted(
        answers,
        key=lambda answer: (
            physical_ir.block_by_id(answer.prompt_block_ids[0]).page_index,
            physical_ir.block_by_id(answer.prompt_block_ids[0]).reading_order,
            answer.question_id,
        ),
    )
    plans: list[PlacementPlan] = []
    result: list[tuple[ConfirmedAnswerForExport, PlacementPlan, str, int]] = []
    for answer in ordered:
        if _contains_rtl(answer.exact_text):
            raise DocumentEngineError(
                "unsupported_rtl",
                "Right-to-left PDF answers are not yet certified for export.",
                recoverable=True,
            )
        evidence = answer.question_evidence()
        exact_question = physical_ir.reconstruct_text(evidence.prompt_block_ids)
        plan = resolve_placement(
            physical_ir,
            evidence,
            answer.exact_text,
            occupied_plans=plans,
        )
        if plan.outcome == "reject":
            raise document_error("unsafe_question_evidence")
        if not hmac.compare_digest(plan.placement_hash, answer.reviewed_placement_hash):
            forced = resolve_placement(
                physical_ir,
                evidence,
                answer.exact_text,
                occupied_plans=plans,
                force_appendix=True,
            )
            if not hmac.compare_digest(forced.placement_hash, answer.reviewed_placement_hash):
                raise document_error("placement_changed")
            plan = forced
        prompt = physical_ir.block_by_id(evidence.prompt_block_ids[0])
        plans.append(plan)
        result.append((answer, plan, exact_question, prompt.page_index + 1))
    return tuple(result)


def _build_job(
    source_pdf: bytes,
    physical_ir: PhysicalDocumentIR,
    worksheet_title: str,
    planned: tuple[tuple[ConfirmedAnswerForExport, PlacementPlan, str, int], ...],
    *,
    max_input_bytes: int,
    max_output_bytes: int,
    max_pages: int,
    font_sha256: str,
) -> PdfRenderJob:
    render_answers: list[RenderAnswer] = []
    for answer, plan, exact_question, source_page in planned:
        if plan.outcome == "inline":
            if plan.region is None or plan.fit is None:
                raise document_error("invalid_physical_evidence")
            render_answers.append(
                RenderAnswer(
                    question_id=_opaque(answer.question_id, "question"),
                    display_identifier=answer.display_identifier,
                    committed_text=answer.exact_text,
                    committed_text_sha256=plan.exact_text_sha256,
                    placement_hash=plan.placement_hash,
                    placement_classification="inline",
                    page_number=plan.region.page_index + 1,
                    lines=tuple(
                        GeneratedLine(
                            text=line.text,
                            separator_after=cast(Any, line.separator_after),
                            x_mpt=line.x_mpt,
                            baseline_y_mpt=line.baseline_y_mpt,
                            font_size_mpt=plan.fit.font_size_mpt,
                        )
                        for line in plan.fit.lines
                    ),
                )
            )
        elif plan.outcome == "appendix":
            paragraphs = tuple(answer.exact_text.split("\n\n"))
            render_answers.append(
                RenderAnswer(
                    question_id=_opaque(answer.question_id, "question"),
                    display_identifier=answer.display_identifier,
                    committed_text=answer.exact_text,
                    committed_text_sha256=plan.exact_text_sha256,
                    placement_hash=plan.placement_hash,
                    placement_classification="appendix",
                    page_number=source_page,
                    continuation=ContinuationInstruction(
                        worksheet_title=worksheet_title,
                        source_question=exact_question,
                        source_page_number=source_page,
                        paragraphs=paragraphs,
                    ),
                )
            )
        else:
            raise document_error("invalid_export")
    return PdfRenderJob(
        schema_version=1,
        operation="render",
        job_id=f"job_{uuid.uuid4().hex}",
        source=SourceBinding(
            source_id=f"source_{physical_ir.source_sha256[:24]}",
            sha256=physical_ir.source_sha256,
            size_bytes=len(source_pdf),
            page_count=len(physical_ir.pages),
            physical_ir_sha256=physical_ir.ir_sha256,
            evidence_version=f"{physical_ir.parser_version}:{physical_ir.schema_version}",
        ),
        limits=ResourceLimits(
            max_input_bytes=max_input_bytes,
            max_output_bytes=max_output_bytes,
            max_pages=max_pages,
        ),
        font_id="noto-sans-regular-v1",
        font_sha256=font_sha256,
        pages=tuple(
            PageGeometry(
                page_number=page.page_index + 1,
                media_box_mpt=tuple(page.media_box_mpt.to_list()),
                crop_box_mpt=tuple(page.crop_box_mpt.to_list()),
                rotation=cast(Any, page.rotation),
                user_unit=page.user_unit,
                canonical_to_pdf_mpt=tuple(page.canonical_to_pdf_mpt.to_list()),
            )
            for page in physical_ir.pages
        ),
        answers=tuple(render_answers),
    )


def _manifest(
    job: PdfRenderJob,
    planned: tuple[tuple[ConfirmedAnswerForExport, PlacementPlan, str, int], ...],
    worksheet_title: str,
    *,
    output_sha256: str,
    continuation_pages: int,
) -> DocumentExportManifest:
    return DocumentExportManifest(
        exporter_version="claros-openpdf-spike-v1",
        source_sha256=job.source.sha256,
        physical_ir_sha256=job.source.physical_ir_sha256,
        worksheet_title_sha256=sha256_hex(worksheet_title.encode("utf-8")),
        source_page_count=job.source.page_count,
        appendix_page_count=continuation_pages,
        output_page_count=job.source.page_count + continuation_pages,
        output_sha256=output_sha256,
        answers=tuple(
            ExportAnswerManifest(
                question_id=answer.question_id,
                exact_question_sha256=plan.exact_question_sha256,
                exact_text_sha256=plan.exact_text_sha256,
                placement_hash=plan.placement_hash,
                outcome=plan.outcome,
                source_page_number=source_page,
                font_size_mpt=plan.fit.font_size_mpt if plan.fit else None,
            )
            for answer, plan, _question, source_page in planned
        ),
    )


def _write_inputs(root: Path, source: bytes, contract: bytes) -> None:
    (root / "tmp").mkdir()
    (root / "source.pdf").write_bytes(source)
    (root / "job.json").write_bytes(contract)
    try:
        (root / "source.pdf").chmod(0o444)
        (root / "job.json").chmod(0o444)
    except OSError:
        pass


def _read_worker_status(root: Path) -> WorkerSuccess | DocumentEngineError:
    payload = _read_bounded(root / "worker-status.json", _MAX_STATUS_BYTES)
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DocumentExecutionFailure("OpenPDF worker response is malformed") from error
    if not isinstance(raw, dict):
        raise DocumentExecutionFailure("OpenPDF worker response is malformed")
    if raw.get("status") == "error":
        if set(raw) != {"schema_version", "status", "code"} or raw.get("schema_version") != 1:
            raise DocumentExecutionFailure("OpenPDF worker response is malformed")
        code = raw.get("code")
        if not isinstance(code, str) or code not in _SAFE_WORKER_CODES:
            raise DocumentExecutionFailure("OpenPDF worker response is malformed")
        messages = {
            "unsupported_rtl": "Right-to-left PDF answers are not yet certified for export.",
            "unsupported_rebuilt_xref": (
                "This PDF requires a full rewrite and cannot use the preservation path."
            ),
            "font_not_allowlisted": "The approved PDF font is unavailable.",
            "resource_limit": "The completed PDF exceeded a safe processing limit.",
        }
        mapped = {
            "invalid_contract": "invalid_export",
            "invalid_pdf": "invalid_export",
        }.get(code, code)
        return DocumentEngineError(
            mapped,
            messages.get(code, "The completed PDF could not be validated safely."),
            recoverable=True,
        )
    try:
        return WorkerSuccess.model_validate(raw, strict=True)
    except ValidationError as error:
        raise DocumentExecutionFailure("OpenPDF worker response is malformed") from error


def _read_validator_status(path: Path, name: str) -> ValidatorSuccess:
    payload = _read_bounded(path, _MAX_STATUS_BYTES)
    try:
        return ValidatorSuccess.model_validate_json(payload, strict=True)
    except ValidationError as error:
        raise DocumentEngineError(
            "invalid_export", f"The independent {name} validation failed.", recoverable=True
        ) from error


def _verify_quarantine_file(path: Path, status: WorkerSuccess, maximum: int) -> None:
    if not path.is_file() or path.is_symlink():
        raise DocumentExecutionFailure("OpenPDF worker omitted quarantined output")
    size = path.stat().st_size
    if size != status.output_bytes or size > maximum or _digest_path(path) != status.output_sha256:
        raise document_error("invalid_export")
    if status.output_pages != status.source_pages + status.continuation_pages:
        raise document_error("invalid_export")


def _read_bounded(path: Path, maximum: int) -> bytes:
    try:
        size = path.stat().st_size
        if size < 1 or size > maximum or path.is_symlink():
            raise DocumentExecutionFailure("bounded artifact has an invalid size")
        return path.read_bytes()
    except OSError as error:
        raise DocumentExecutionFailure("bounded artifact is unavailable") from error


def _safe_environment(job_root: Path) -> dict[str, str]:
    allowed = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "JAVA_HOME"}
    }
    allowed["TMP"] = str(job_root / "tmp")
    allowed["TEMP"] = str(job_root / "tmp")
    allowed["NO_PROXY"] = "*"
    return allowed


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _process_rss(pid: int) -> int | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            handle = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
            if not handle:
                return None
            try:
                counters = Counters()
                counters.cb = ctypes.sizeof(counters)
                if not ctypes.windll.psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(counters), counters.cb
                ):
                    return None
                return int(counters.PeakWorkingSetSize)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except (AttributeError, OSError, ValueError):
            return None
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
        match = re.search(r"^VmHWM:\s+(\d+)\s+kB$", status, re.MULTILINE)
        return int(match.group(1)) * 1024 if match else None
    except (OSError, ValueError):
        return None


def _max_optional(first: int | None, second: int | None) -> int | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def _digest_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _cleanup_job(root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            with suppress(OSError):
                path.chmod(0o600)
    shutil.rmtree(root)


def _contains_rtl(text: str) -> bool:
    return any(unicodedata.bidirectional(character) in _RTL_BIDI for character in text)


def _opaque(value: str, kind: str) -> str:
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{7,95}", value):
        return value
    return f"{kind}_{sha256_hex(value.encode('utf-8'))[:24]}"
