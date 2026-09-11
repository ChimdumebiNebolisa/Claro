from __future__ import annotations

import asyncio
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(EXPERIMENT))

from openpdf_integration.adapter import (  # noqa: E402
    OpenPdfWorkerExportEngine,
    SpikeRuntime,
)

from backend.document import (  # noqa: E402
    ConfirmedAnswerForExport,
    QuestionEvidence,
    extract_physical_ir,
    resolve_placement,
)
from backend.tests.document.factories import worksheet_pdf  # noqa: E402


def sample():
    source = worksheet_pdf()
    physical_ir = extract_physical_ir(source)
    prompt = next(
        block
        for block in physical_ir.pages[0].blocks
        if block.kind == "text" and block.text and block.text.endswith("?")
    )
    question = QuestionEvidence("benchmark-question-1", "Question 1", (prompt.id,))
    text = "The office keeps official files efficient, exact, and independently validated."
    plan = resolve_placement(physical_ir, question, text)
    answer = ConfirmedAnswerForExport(
        question.question_id,
        question.display_identifier,
        question.prompt_block_ids,
        (),
        text,
        plan.placement_hash,
    )
    return source, physical_ir, answer


async def one(root: Path) -> dict[str, int | None]:
    source, physical_ir, answer = sample()
    engine = OpenPdfWorkerExportEngine(runtime=SpikeRuntime(work_root=root))
    started = time.perf_counter()
    await engine.export(source, physical_ir, "Benchmark worksheet", (answer,), timeout_seconds=90)
    elapsed = round((time.perf_counter() - started) * 1000)
    evidence = engine.last_evidence
    worker_process = next(item for item in evidence.processes if item.label == "openpdf")
    process_times = {item.label: item.duration_ms for item in evidence.processes}
    return {
        "total_ms": elapsed,
        "worker_process_ms": worker_process.duration_ms,
        "worker_internal_render_ms": evidence.worker_internal_render_ms,
        "cold_start_overhead_ms": max(
            0, worker_process.duration_ms - evidence.worker_internal_render_ms
        ),
        "validation_ms": evidence.validation_ms,
        "qpdf_ms": process_times["qpdf"],
        "pdfbox_ms": process_times["pdfbox"],
        "pdfjs_ms": process_times["pdfjs"],
        "peak_worker_rss_bytes": evidence.peak_worker_rss_bytes,
        "output_bytes": evidence.output_bytes,
        "temporary_peak_bytes": evidence.temporary_peak_bytes,
        "cleanup_ms": evidence.cleanup_ms,
    }


def aggregate(rows: list[dict[str, int | None]]) -> dict[str, object]:
    numeric = [key for key in rows[0] if all(row[key] is not None for row in rows)]
    return {
        "jobs": len(rows),
        "wall_ms": max(int(row["total_ms"] or 0) for row in rows),
        "mean": {
            key: round(statistics.mean(int(row[key] or 0) for row in rows)) for key in numeric
        },
        "max": {key: max(int(row[key] or 0) for row in rows) for key in numeric},
    }


async def main() -> None:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else EXPERIMENT / "benchmark-output.json"
    result: dict[str, object] = {
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "note": "Developer-workstation evidence; not a production throughput claim.",
        },
        "concurrency": {},
    }
    with tempfile.TemporaryDirectory(prefix="claros-openpdf-benchmark-") as temporary:
        root = Path(temporary)
        for count in (1, 5, 10):
            started = time.perf_counter()
            rows = await asyncio.gather(*(one(root) for _ in range(count)))
            summary = aggregate(rows)
            summary["batch_wall_ms"] = round((time.perf_counter() - started) * 1000)
            result["concurrency"][str(count)] = summary

        fake = EXPERIMENT / "tests" / "helpers" / "fake_worker.py"
        source, physical_ir, answer = sample()
        failed_engine = OpenPdfWorkerExportEngine(
            runtime=SpikeRuntime(
                work_root=root,
                worker_command_override=(sys.executable, str(fake), "crash"),
            )
        )
        started = time.perf_counter()
        try:
            await failed_engine.export(
                source, physical_ir, "Benchmark worksheet", (answer,), timeout_seconds=10
            )
        except Exception:
            result["failure_path_ms"] = round((time.perf_counter() - started) * 1000)
        result["failure_cleanup_ms"] = failed_engine.last_evidence.cleanup_ms
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
