# OpenPDF production-architecture spike results

Evidence date: 2026-09-05. Branch baseline: `5b20728d0a532d4d75a58bcb31bd4f61afdefe49`. Host: Windows 10 build 26200, Python 3.11.9, Java 21.0.10, Maven 3.9.11, qpdf 12.3.2, PDF.js 4.8.69, Playwright 1.58.2. This is workstation evidence, not a throughput claim.

## 1. What was implemented

- a strict renderer-neutral job contract validated independently in Python and Java;
- a separate Java/OpenPDF 3.0.5 worker using incremental stamping, explicit transforms, Identity-H embedded Noto Sans, and disabled non-RTL glyph substitution;
- explicit RTL and rebuilt-xref rejection;
- a per-job quarantine and all-or-nothing release supervisor;
- independent qpdf, PDFBox, and PDF.js validation processes;
- an experimental adapter over Claros's existing document-executor seam;
- a development/test-only `CLAROS_PDF_ENGINE=current|openpdf-spike` selector whose default is current and whose spike value is rejected in production;
- real Claros API end-to-end tests, bounded failure injection, resource probes, and a concurrency benchmark;
- a non-root/read-only/no-network Docker boundary specification, not a production deployment.

No production code or production configuration changed.

## 2. Exact architecture tested

The real `AssignmentApplicationService` performed upload/load, plan, review, commit, source-object revalidation, export start/failure/completion, and immutable publication. Only its already-existing injected `document_executor` was replaced in the test application. The adapter received the existing `confirmed_answers_for_export` projection, never draft/candidate/transcript state.

OpenPDF wrote `quarantine/derivative.pdf`. The supervisor ran qpdf, a PDFBox-only semantic process, and a browser PDF.js process. Only then did it read bytes and return `RenderedExport` to the unchanged service publisher. Source, contract, and derivative hashes were checked again immediately before release.

See `architecture.md` for the contract and threat boundary.

## 3. Security controls

Summary: 14 ENFORCED, 3 SIMULATED, 5 UNVERIFIED. The unresolved control categories are OS-enforced no-egress, read-only runtime, non-root identity, CPU, and PID/thread limits. The complete container image also remains unbuilt. The full per-control evidence is in `architecture.md`.

The local worker process is meaningful for crash/timeout containment but is not a production sandbox: it ran as the developer account and retained ambient host filesystem/network access. The Docker specification declares the intended controls, but `docker version` failed to connect to the Docker Desktop Linux engine. None of those container-only controls are claimed as enforced.

## 4. End-to-end Claros export

PASS. A real HTTP flow committed one inline ligature-heavy answer and one long continuation answer, then created an uncommitted third-question draft. The released derivative contained both exact committed answers, did not contain the draft sentinel, preserved the source SHA-256, reproduced the reviewed placement, produced multiple numbered continuation pages, and passed all validators. The per-job directory was removed.

The existing service did not create a PDF object until the gate returned. On worker crash, worker timeout, and independent-validator rejection, it recorded a recoverable failed export while the exact confirmed answer remained available unchanged.

## 5. Failure injection

| Case | Result | Release/state evidence |
|---|---|---|
| Worker process crash | PASS | Non-zero exit; no bytes released; committed state retained. |
| Worker timeout | PASS | JVM/helper killed and reaped; API returned recoverable `export_timeout`; state retained. |
| Malformed worker response | PASS | Strict response parse rejected it. |
| Output fails qpdf | PASS | Invalid PDF had a well-formed worker status but qpdf blocked release. |
| Exact extraction disagreement | PASS | A syntactically valid wrong-text derivative was blocked by PDFBox; copying the untouched source was also blocked. |
| Source hash changes after commit | PASS | Rejected as `stale_source` before launch. |
| Placement evidence changes after commit | PASS | Recomputed placement binding rejected as `placement_changed`. |
| Unsupported RTL answer | PASS | Explicit recoverable `unsupported_rtl` before launch; Java independently rejects it too. |
| Output exceeds limit | PASS | Counting stream returned `resource_limit`; fake over-limit output was also rejected. |
| Input exceeds limit | PASS | Rejected before PDF parsing. |
| Malformed/rebuilt xref | PASS | Deterministic damaged `startxref` classified `unsupported_rebuilt_xref`; no full rewrite. |
| Missing allowlisted font | PASS | Rejected `font_not_allowlisted` before launch. |
| Cleanup after failure | PASS | Every injected path left zero active processes and no job/quarantine directory. |
| Wrong physical coordinate | PASS | Valid derivative with a 50 pt displacement was rejected by PDFBox text-position measurement. |
| Worker mutates authority contract | PASS | Contract hash mismatch rejected before validation. |

There is no silent control-renderer fallback in any case.

## 6. Resource-limit probes

| Probe | Result | Actual enforcement |
|---|---|---|
| Oversized input before parse | PASS | Python byte check; Java repeats it. |
| Excessive page count | PASS | Stored evidence and Java discovered count. |
| Compressed/object-stream source | PASS | Bounded synthetic object-stream PDF rendered and passed all gates. This was not a decompression-bomb test. |
| Long continuation output | PASS | 95 repeated exact Unicode sentences crossed at least two pages and remained within output limits. |
| JVM over memory budget | PASS | 96 MiB bounded allocation under `-Xmx32m` exited non-zero. OS/container memory kill remains unverified. |
| Wall-clock overrun | PASS | 150 ms injected deadline killed and reaped the process and cleaned the job. |
| Temporary disk quota | PARTIAL | Output and cleanup bounds are enforced; host per-directory storage quota was unavailable. |
| CPU and PID/thread quotas | UNVERIFIED | Declared in Docker launcher only; daemon unavailable. |

No dangerous system-wide exhaustion test was attempted.

## 7. Benchmark

`scripts/run-benchmark.py` used one native-text Letter worksheet with one exact ligature-heavy inline answer. Each job launched a cold OpenPDF JVM plus qpdf, PDFBox, and a cold headless Chromium/PDF.js validator. Values are from `benchmark-output.json`.

| Concurrent jobs | Batch wall | Mean total/job | Mean OpenPDF process | Mean internal render | Mean cold JVM overhead | Mean validation | Max worker RSS/job |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 9.325 s | 9.194 s | 1.781 s | 1.333 s | 0.448 s | 6.781 s | 75,149,312 B |
| 5 | 19.581 s | 18.634 s | 2.341 s | 1.783 s | 0.557 s | 15.063 s | 74,711,040 B |
| 10 | 49.100 s | 46.959 s | 4.997 s | 3.941 s | 1.056 s | 38.520 s | 74,756,096 B |

Output was 14,860 bytes/job; peak measured per-job temporary data was 18,477 bytes. Mean cleanup was 31 ms at concurrency 1, 85 ms at 5, and 390 ms at 10. The injected crash path returned in 610 ms and cleanup took 15 ms.

Interpretation: JVM start/render is not the obvious bottleneck; independent browser/PDFBox validation dominates. Ten simultaneous cold browsers materially increase latency, so the production worker should start at concurrency 1 and measure warm validator reuse only if process isolation and cross-job data clearing remain provable. The benchmark does not establish production throughput.

## 8. Deployment implications

The current image is Python 3.11 only. Real adoption requires Java 21, OpenPDF/FOP, PDFBox, qpdf, Node, Playwright, Chromium, an isolated supervisor, and a denied-egress network. The shaded Java artifact alone is 18,431,871 bytes; full image size was not measured.

A same-process or same-container JVM is insufficient. A Cloud Run sidecar shares its instance network namespace, so the smallest credible boundary is a second stateless internal Cloud Run PDF-pipeline service with authenticated API-only ingress, all-traffic VPC egress routed to deny rules, no application/GCS credentials, concurrency 1 initially, dedicated CPU/memory/deadline, and per-request cleanup. Claros API remains the only assignment/state/publish authority; no queue is required for the existing synchronous P0 flow.

Encrypted PDFs remain unsupported. Therefore the topology transports and logs no PDF password. If encrypted ownership is reconsidered, password transport, lifetime, redaction, and zeroization require a separate design.

## 9. Validation latency and cost

At concurrency 1 the independent gates consumed 6.781 s of the 9.194 s mean total: qpdf 0.109 s, PDFBox 2.797 s, and PDF.js/Chromium 3.875 s. At concurrency 10, PDFBox alone averaged 28.406 s and total validation averaged 38.520 s. No warm-pool optimization was attempted because it can weaken job isolation and cleanup.

The operational cost is an additional private service, a larger multi-runtime image, a VPC/firewall egress boundary, and more CPU/memory per export. These costs look plausible, not yet production-proven.

## 10. Known unsupported or unverified cases

- all RTL generated text: explicit fail closed;
- any PDF for which OpenPDF rebuilds xref: explicit fail closed, no rewrite fallback;
- encrypted PDFs/password transport: unsupported by current Claros preflight and this contract;
- container-enforced egress/filesystem/user/CPU/PID limits: unverified locally;
- production Linux image build, startup, image size, health checks, and Cloud Run latency: unverified;
- production-scale throughput or warm process reuse: not claimed.

## 11. Changes required before real production adoption

1. Build and run the complete Linux worker/validator image in CI with non-root, read-only root, no-network/denied-egress, memory/CPU/PID/tmpfs limits, timeout kill, and post-job cleanup assertions.
2. Deploy a private staging worker service with API-only IAM invocation and all-traffic VPC egress deny policy; prove it cannot reach the internet or storage.
3. Measure Linux/container image size, cold/warm latency, peak total instance memory including Chromium, and concurrency 1 under Cloud Run.
4. Add health/startup probes and privacy-log canaries; preserve only bounded metadata.
5. Decide whether PDF.js must run per job or whether a cheaper independently isolated renderer can meet the same semantic gate without weakening it.
6. Only after those gates pass, propose—not perform—the production setting/adapter wiring and migration rollout.

## 12. Current renderer control path

Intact. No production file changed, `current` is the selector default, `openpdf-spike` is blocked for `environment="production"`, and the existing Claros tests continue to exercise the current renderer.

## 13. Commands and actual outputs

```text
mvn -q package -DskipTests
  exit 0; shaded JAR 18,431,871 bytes

.venv/Scripts/python.exe -m pytest -q experiments/openpdf-integration/tests
  exit 0; 23 passed, 0 failed, 1 warning in 118.25s

$trackedTests = @(git ls-files 'backend/tests/**/test_*.py')
.venv/Scripts/python.exe -m pytest -q $trackedTests
  exit 0; 33 tracked test files; 392 passed, 0 failed, 23 warnings in 128.35s

powershell -NoProfile -ExecutionPolicy Bypass -File experiments/openpdf-hostile/scripts/run.ps1
  exit 0; 6 JUnit tests, 0 failures; 33 derivatives;
  PDF.js rendered 33/33; merged report unchanged at 31 PASS / 2 RTL PARTIAL

.venv/Scripts/python.exe experiments/openpdf-integration/scripts/run-benchmark.py experiments/openpdf-integration/benchmark-output.json
  exit 0; current validator code; concurrency 1/5/10 completed;
  batch wall 9.325s / 19.581s / 49.100s; metrics in section 7

docker version
  client 29.1.2 present; failed to connect to Docker Desktop Linux engine
```

## Final recommendation

**B. PDF correctness passed, but runtime/isolation architecture needs more work.**
