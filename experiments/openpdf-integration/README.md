# Claros isolated OpenPDF integration spike

This directory tests one production-shaped path without changing or selecting Claros's production PDF renderer. It consumes only committed-answer projections and server-owned placement evidence, launches OpenPDF 3.0.5 in a separate JVM, holds its derivative in a per-job quarantine directory, and releases bytes only after qpdf, PDFBox, and PDF.js agree.

The spike reuses the existing `AssignmentApplicationService(document_executor=...)` seam. No production module imports this experiment. The experimental selector defaults to `CLAROS_PDF_ENGINE=current`; `openpdf-spike` is rejected when `environment == "production"` because this task does not authorize migration.

## Prerequisites

- Python 3.11 and the repository `.venv`
- Java 21 and Maven
- Node dependencies already installed, including PDF.js, Playwright, and Chromium
- qpdf on `PATH`, or the checksum-pinned hostile-harness bootstrap at `../openpdf-hostile/scripts/bootstrap-qpdf.ps1`

The only font is the repository's SIL Open Font License 1.1 Noto Sans Regular fixture at `assets/fonts/noto-sans/NotoSans-Regular.ttf`. The worker accepts font ID `noto-sans-regular-v1` only and verifies SHA-256 `b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5` before use.

## Run

```powershell
Push-Location experiments/openpdf-integration
mvn test package
Pop-Location

.venv/Scripts/python.exe -m pytest -q experiments/openpdf-integration/tests
.venv/Scripts/python.exe experiments/openpdf-integration/scripts/run-benchmark.py experiments/openpdf-integration/benchmark-output.json
```

The Docker boundary is specified in `worker/Dockerfile` and `scripts/run-worker-container.ps1`. Build it from the repository root:

```powershell
docker build -f experiments/openpdf-integration/worker/Dockerfile -t claros-openpdf-worker-spike:local .
```

The Docker daemon was unavailable on the evidence host, so the container controls are specifications, not locally proven enforcement. See [architecture.md](architecture.md) and [results.md](results.md).

## What is deliberately absent

- no production setting or endpoint change
- no renderer choice exposed to clients
- no URLs, filesystem paths, font paths, HTML, shell arguments, renderer classes, or storage credentials in the job contract
- no RTL rendering
- no xref-rebuild/full-rewrite fallback
- no direct publication from the OpenPDF worker
- no fallback to the current renderer after a spike-path failure
