"""Killable process boundary for untrusted PDF analysis and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias, cast

import anyio
from pydantic import TypeAdapter, ValidationError

from backend.document import (
    ConfirmedAnswerForExport,
    DocumentEngineError,
    PreflightLimits,
    build_export,
    extract_physical_ir,
    parse_physical_ir,
    preflight_pdf,
    resolve_placement,
)
from backend.document.errors import document_error
from backend.document.geometry import QuestionEvidence
from backend.document.models import PhysicalDocumentIR
from backend.document.preflight import validate_question_count
from backend.domain import (
    PlacementCapability as DomainPlacementCapability,
)
from backend.domain import QuestionState

_ROOT = Path(__file__).resolve().parents[1]
_MAX_STATUS_BYTES = 16 * 1024
_MAX_IR_BYTES = 64 * 1024 * 1024
_MAX_EXPORT_BYTES = 64 * 1024 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_QUESTION_PREFIX = re.compile(
    r"^\s*(?:(?:question|q)\s*)?(?P<label>\d{1,2}|[A-Za-z])\s*[.)\-:]\s*",
    re.IGNORECASE,
)
_QUESTION_LABEL = re.compile(
    r"^\s*(?:(?:question|q)\s*)?(?P<label>\d{1,2}|[A-Za-z])\s*[.)\-:]?\s*$",
    re.IGNORECASE,
)
_QUESTION_ADAPTER = TypeAdapter(tuple[QuestionState, ...])


class DocumentExecutionTimeout(TimeoutError):
    """The parent killed and reaped document work at its hard deadline."""


class DocumentExecutionFailure(RuntimeError):
    """The isolated worker failed without a student-safe document reason."""


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    physical_ir: PhysicalDocumentIR
    questions: tuple[QuestionState, ...]


@dataclass(frozen=True, slots=True)
class RenderedExport:
    pdf_bytes: bytes
    manifest_bytes: bytes


JobValue: TypeAlias = str | int | list[dict[str, object]] | dict[str, int]
Job = dict[str, JobValue]


class DocumentProcessExecutor:
    """Run one document job per subprocess so a timeout can stop actual work."""

    def __init__(self, *, worker_module: str = "backend.document_execution") -> None:
        if not worker_module or any(character.isspace() for character in worker_module):
            raise ValueError("worker_module must be an importable module name")
        self._worker_module = worker_module
        self._lock = threading.Lock()
        self._active: dict[int, subprocess.Popen[bytes]] = {}
        self._last_worker_returncode: int | None = None

    @property
    def active_process_count(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def last_worker_returncode(self) -> int | None:
        with self._lock:
            return self._last_worker_returncode

    async def analyze(
        self,
        source_pdf: bytes,
        *,
        limits: PreflightLimits,
        timeout_seconds: float,
    ) -> AnalysisResult:
        outputs = await self._run_job(
            job={
                "operation": "analyze",
                "limits": {
                    "max_upload_bytes": limits.max_upload_bytes,
                    "max_pages": limits.max_pages,
                    "max_questions": limits.max_questions,
                    "max_extracted_text_bytes": limits.max_extracted_text_bytes,
                    "min_selectable_characters": limits.min_selectable_characters,
                },
            },
            inputs={"source.pdf": source_pdf},
            expected_outputs={
                "physical-ir.json": _MAX_IR_BYTES,
                "questions.json": _MAX_IR_BYTES,
            },
            timeout_seconds=timeout_seconds,
        )
        try:
            physical_ir, questions = await anyio.to_thread.run_sync(
                _parse_analysis_outputs,
                outputs["physical-ir.json"],
                outputs["questions.json"],
                abandon_on_cancel=True,
            )
        except (DocumentEngineError, ValidationError, ValueError, TypeError) as error:
            raise DocumentExecutionFailure("document worker returned invalid analysis") from error
        return AnalysisResult(physical_ir=physical_ir, questions=questions)

    async def export(
        self,
        source_pdf: bytes,
        physical_ir: PhysicalDocumentIR,
        worksheet_title: str,
        answers: tuple[ConfirmedAnswerForExport, ...],
        *,
        timeout_seconds: float,
    ) -> RenderedExport:
        answer_payload: list[dict[str, object]] = [
            {
                "question_id": answer.question_id,
                "display_identifier": answer.display_identifier,
                "prompt_block_ids": list(answer.prompt_block_ids),
                "context_block_ids": list(answer.context_block_ids),
                "exact_text": answer.exact_text,
                "reviewed_placement_hash": answer.reviewed_placement_hash,
            }
            for answer in answers
        ]
        outputs = await self._run_job(
            job={
                "operation": "export",
                "worksheet_title": worksheet_title,
                "answers": answer_payload,
            },
            inputs={
                "source.pdf": source_pdf,
                "physical-ir.json": physical_ir.canonical_bytes(),
            },
            expected_outputs={
                "completed.pdf": _MAX_EXPORT_BYTES,
                "export-manifest.json": _MAX_MANIFEST_BYTES,
            },
            timeout_seconds=timeout_seconds,
        )
        return RenderedExport(
            pdf_bytes=outputs["completed.pdf"],
            manifest_bytes=outputs["export-manifest.json"],
        )

    async def _run_job(
        self,
        *,
        job: Job,
        inputs: dict[str, bytes],
        expected_outputs: dict[str, int],
        timeout_seconds: float,
    ) -> dict[str, bytes]:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deadline = anyio.current_time() + timeout_seconds
        job_root = Path(tempfile.mkdtemp(prefix="claros-document-"))
        process: subprocess.Popen[bytes] | None = None
        try:
            await anyio.to_thread.run_sync(_write_job_files, job_root, job, inputs)
            if anyio.current_time() >= deadline:
                raise DocumentExecutionTimeout("document job timed out before launch")
            process = await anyio.to_thread.run_sync(self._start_process, job_root)
            self._register(process)
            await self._wait_for_process(process, deadline)
            if process.returncode != 0:
                raise DocumentExecutionFailure("document worker exited unexpectedly")
            status = await self._read_file(
                job_root / "status.json", _MAX_STATUS_BYTES, deadline=deadline
            )
            decoded = _decode_status(status)
            if decoded["status"] == "document_error":
                raise DocumentEngineError(
                    cast(str, decoded["code"]),
                    cast(str, decoded["message"]),
                    recoverable=cast(bool, decoded["recoverable"]),
                )
            if decoded["status"] != "ok":
                raise DocumentExecutionFailure("document worker failed safely")
            return {
                name: await self._read_file(job_root / name, limit, deadline=deadline)
                for name, limit in expected_outputs.items()
            }
        except BaseException:
            if process is not None:
                with anyio.CancelScope(shield=True):
                    await self._terminate_and_reap(process)
            raise
        finally:
            if process is not None:
                with anyio.CancelScope(shield=True):
                    await self._reap_finished(process)
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(shutil.rmtree, job_root, True)

    def _start_process(self, job_root: Path) -> subprocess.Popen[bytes]:
        kwargs: dict[str, object] = {
            "cwd": str(_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", self._worker_module, "--job-dir", str(job_root)],
            **kwargs,
        )

    def _register(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._active[process.pid] = process

    def _record_reaped(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._active.pop(process.pid, None)
            self._last_worker_returncode = process.returncode

    async def _wait_for_process(self, process: subprocess.Popen[bytes], deadline: float) -> None:
        while process.poll() is None:
            remaining = deadline - anyio.current_time()
            if remaining <= 0:
                raise DocumentExecutionTimeout("document job exceeded its deadline")
            await anyio.sleep(min(0.02, remaining))

    async def _terminate_and_reap(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await anyio.to_thread.run_sync(process.wait)
        self._record_reaped(process)

    async def _reap_finished(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            return
        await anyio.to_thread.run_sync(process.wait)
        self._record_reaped(process)

    @staticmethod
    async def _read_file(path: Path, maximum: int, *, deadline: float) -> bytes:
        remaining = deadline - anyio.current_time()
        if remaining <= 0:
            raise DocumentExecutionTimeout("document result exceeded its deadline")
        try:
            with anyio.fail_after(remaining):
                return await anyio.to_thread.run_sync(
                    _read_bounded,
                    path,
                    maximum,
                    abandon_on_cancel=True,
                )
        except TimeoutError as error:
            raise DocumentExecutionTimeout("document result exceeded its deadline") from error


def _write_job_files(job_root: Path, job: Job, inputs: dict[str, bytes]) -> None:
    for name, data in inputs.items():
        (job_root / name).write_bytes(data)
    (job_root / "job.json").write_bytes(_json_bytes(job))


def _read_bounded(path: Path, maximum: int) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise DocumentExecutionFailure("document worker omitted an output") from error
    if size < 1 or size > maximum:
        raise DocumentExecutionFailure("document worker output has an invalid size")
    try:
        return path.read_bytes()
    except OSError as error:
        raise DocumentExecutionFailure("document worker output is unreadable") from error


def _decode_status(payload: bytes) -> dict[str, object]:
    try:
        result = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DocumentExecutionFailure("document worker status is invalid") from error
    if not isinstance(result, dict) or result.get("status") not in {
        "ok",
        "document_error",
        "internal_error",
    }:
        raise DocumentExecutionFailure("document worker status is invalid")
    if result["status"] == "document_error" and (
        not isinstance(result.get("code"), str)
        or not isinstance(result.get("message"), str)
        or not isinstance(result.get("recoverable"), bool)
    ):
        raise DocumentExecutionFailure("document worker error is invalid")
    return cast(dict[str, object], result)


def _parse_analysis_outputs(
    physical_ir_bytes: bytes, questions_bytes: bytes
) -> tuple[PhysicalDocumentIR, tuple[QuestionState, ...]]:
    return (
        parse_physical_ir(physical_ir_bytes),
        _QUESTION_ADAPTER.validate_json(questions_bytes, strict=True),
    )


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _worker(job_root: Path) -> None:
    try:
        raw_job = json.loads((job_root / "job.json").read_bytes())
        if not isinstance(raw_job, dict):
            raise ValueError("invalid job")
        operation = raw_job.get("operation")
        source_pdf = (job_root / "source.pdf").read_bytes()
        if operation == "analyze":
            _worker_analyze(job_root, source_pdf, raw_job)
        elif operation == "export":
            _worker_export(job_root, source_pdf, raw_job)
        else:
            raise ValueError("invalid operation")
        _write_status(job_root, {"status": "ok"})
    except DocumentEngineError as error:
        _write_status(
            job_root,
            {
                "status": "document_error",
                "code": error.code,
                "message": error.safe_message,
                "recoverable": error.recoverable,
            },
        )
    except Exception:
        _write_status(job_root, {"status": "internal_error"})


def _worker_analyze(job_root: Path, source_pdf: bytes, job: dict[str, object]) -> None:
    raw_limits = job.get("limits")
    if not isinstance(raw_limits, dict):
        raise ValueError("invalid limits")
    limits = PreflightLimits(
        max_upload_bytes=_positive_int(raw_limits.get("max_upload_bytes")),
        max_pages=_positive_int(raw_limits.get("max_pages")),
        max_questions=_positive_int(raw_limits.get("max_questions")),
        max_extracted_text_bytes=_positive_int(raw_limits.get("max_extracted_text_bytes")),
        min_selectable_characters=_positive_int(raw_limits.get("min_selectable_characters")),
    )
    preflight = preflight_pdf(source_pdf, limits=limits)
    physical_ir = extract_physical_ir(source_pdf, preflight=preflight)
    questions = ground_questions(physical_ir, limits=limits)
    (job_root / "physical-ir.json").write_bytes(physical_ir.canonical_bytes())
    (job_root / "questions.json").write_bytes(
        _json_bytes([question.model_dump(mode="json") for question in questions])
    )


def _worker_export(job_root: Path, source_pdf: bytes, job: dict[str, object]) -> None:
    worksheet_title = job.get("worksheet_title")
    raw_answers = job.get("answers")
    if not isinstance(worksheet_title, str) or not isinstance(raw_answers, list):
        raise ValueError("invalid export job")
    physical_ir = parse_physical_ir((job_root / "physical-ir.json").read_bytes())
    answers = tuple(_export_answer(item) for item in raw_answers)
    artifact = build_export(source_pdf, physical_ir, worksheet_title, answers)
    (job_root / "completed.pdf").write_bytes(artifact.pdf_bytes)
    (job_root / "export-manifest.json").write_bytes(artifact.manifest.canonical_bytes())


def _export_answer(raw: object) -> ConfirmedAnswerForExport:
    if not isinstance(raw, dict):
        raise ValueError("invalid export answer")
    return ConfirmedAnswerForExport(
        question_id=_string(raw.get("question_id")),
        display_identifier=_string(raw.get("display_identifier")),
        prompt_block_ids=_string_tuple(raw.get("prompt_block_ids")),
        context_block_ids=_string_tuple(raw.get("context_block_ids")),
        exact_text=_string(raw.get("exact_text")),
        reviewed_placement_hash=_string(raw.get("reviewed_placement_hash")),
    )


def _write_status(job_root: Path, status: dict[str, object]) -> None:
    temporary = job_root / "status.tmp"
    temporary.write_bytes(_json_bytes(status))
    os.replace(temporary, job_root / "status.json")


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected a positive integer")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("expected a string")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected a string list")
    return tuple(cast(list[str], value))


def ground_questions(
    physical_ir: PhysicalDocumentIR, *, limits: PreflightLimits
) -> tuple[QuestionState, ...]:
    candidates: list[tuple[Any, Any, str, Any | None]] = []
    for page in physical_ir.pages:
        text_blocks = tuple(
            block for block in page.blocks if block.kind == "text" and block.text is not None
        )
        for block in text_blocks:
            if block.text is None:
                continue
            exact_prompt = physical_ir.reconstruct_text((block.id,))
            prefix = _QUESTION_PREFIX.match(exact_prompt)
            if prefix is None and "?" not in exact_prompt:
                continue
            label_block = _nearest_question_label(block, text_blocks)
            if prefix is None and label_block is None:
                continue
            label_match = (
                _QUESTION_LABEL.fullmatch(label_block.text)
                if label_block is not None and label_block.text is not None
                else None
            )
            display_identifier = (
                prefix.group("label")
                if prefix is not None
                else cast(re.Match[str], label_match).group("label")
            )
            candidates.append(
                (
                    page,
                    block,
                    display_identifier,
                    _following_instruction(block, text_blocks),
                )
            )

    if not candidates:
        for page in physical_ir.pages:
            for block in page.blocks:
                if block.kind == "text" and block.text is not None and "?" in block.text:
                    candidates.append((page, block, str(len(candidates) + 1), None))

    if not candidates:
        raise document_error("ambiguous_question_boundaries")
    validate_question_count(len(candidates), limits)
    questions = []
    for index, (page, block, display_identifier, instruction) in enumerate(candidates, start=1):
        context_block_ids = (instruction.id,) if instruction is not None else ()
        question_id = f"q_{hashlib.sha256(block.id.encode('ascii')).hexdigest()[:16]}"
        evidence = QuestionEvidence(
            question_id=question_id,
            display_identifier=display_identifier,
            prompt_block_ids=(block.id,),
            context_block_ids=context_block_ids,
        )
        plan = resolve_placement(physical_ir, evidence, "Sample answer")
        questions.append(
            QuestionState(
                question_id=question_id,
                index=index,
                display_identifier=display_identifier,
                exact_prompt=physical_ir.reconstruct_text((block.id,)),
                prompt_block_ids=evidence.prompt_block_ids,
                context_block_ids=evidence.context_block_ids,
                instruction=(
                    physical_ir.reconstruct_text(context_block_ids) if context_block_ids else None
                ),
                page_number=page.page_index + 1,
                placement_capability=(
                    DomainPlacementCapability.INLINE_POSSIBLE
                    if plan.outcome == "inline"
                    else DomainPlacementCapability.APPENDIX_ONLY
                ),
            )
        )
    return tuple(questions)


def _nearest_question_label(block: Any, text_blocks: tuple[Any, ...]) -> Any | None:
    vertical_center = (block.bbox.y0 + block.bbox.y1) // 2
    matches = []
    for candidate in text_blocks:
        if candidate.id == block.id or candidate.text is None:
            continue
        if _QUESTION_LABEL.fullmatch(candidate.text) is None:
            continue
        candidate_center = (candidate.bbox.y0 + candidate.bbox.y1) // 2
        vertical_distance = abs(candidate_center - vertical_center)
        horizontal_gap = block.bbox.x0 - candidate.bbox.x1
        if vertical_distance <= 8_000 and 0 <= horizontal_gap <= 90_000:
            matches.append((vertical_distance, horizontal_gap, candidate.reading_order, candidate))
    return min(matches, default=(0, 0, 0, None))[-1]


def _following_instruction(block: Any, text_blocks: tuple[Any, ...]) -> Any | None:
    matches = []
    for candidate in text_blocks:
        if candidate.reading_order <= block.reading_order or candidate.text is None:
            continue
        if _nearest_question_label(candidate, text_blocks) is not None:
            continue
        vertical_gap = candidate.bbox.y0 - block.bbox.y1
        horizontal_delta = abs(candidate.bbox.x0 - block.bbox.x0)
        if 0 <= vertical_gap <= 36_000 and horizontal_delta <= 18_000:
            matches.append((vertical_gap, candidate.reading_order, candidate))
    return min(matches, default=(0, 0, None))[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    args = parser.parse_args()
    _worker(cast(Path, args.job_dir))


if __name__ == "__main__":
    main()
