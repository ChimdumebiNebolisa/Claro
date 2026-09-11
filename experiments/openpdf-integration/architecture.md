# Architecture and threat boundary

## Decision scope

This spike asks whether Claros can preserve its current domain invariants while substituting an isolated renderer for one explicitly selected development/test export. It does not authorize production selection. The current ReportLab/pypdf executor remains unchanged and remains the default.

## Tested flow

```text
AssignmentApplicationService (sole owner of assignment/commit state)
  -> confirmed_answers_for_export() only
  -> stored immutable source bytes + stored PhysicalDocumentIR
  -> experimental OpenPdfWorkerExportEngine
       1. re-hash source and recompute reviewed placements from server evidence
       2. create strict canonical PdfRenderJob and per-job directory
       3. separate Java 21 process: OpenPDF incremental stamping
       4. quarantine/derivative.pdf (not read or returned yet)
       5. qpdf --check process
       6. PDFBox semantic/extraction/coordinate/render process
       7. PDF.js extraction/canvas-render process
       8. re-hash source, contract, and derivative
       9. read and release derivative bytes only after every gate passes
  -> existing immutable object publication and export completion
```

The service writes no completed PDF object until the adapter returns. Any exception follows the existing `fail_export` path, which preserves confirmed answers. There is no automatic fallback: selecting the spike and failing it returns a recoverable error.

## Renderer-neutral job contract

`openpdf_integration/contract.py` is the authority boundary. Pydantic validates a strict, extra-forbidden model in the supervisor; `ContractSupport.java` independently checks exact object keys, types, ranges, hashes, reconstruction, unique IDs, page sequence, and limits in the JVM.

The contract contains:

- opaque job and source IDs;
- source SHA-256, byte length, page count, physical-IR SHA-256, and parser/schema evidence version;
- byte/page limits;
- a fixed font ID and expected font checksum;
- MediaBox, CropBox, rotation, UserUnit, and canonical-to-PDF transform for every source page;
- only committed answer text and its SHA-256;
- approved placement hash/classification and source page;
- exact server-produced physical line baselines for inline placements; or
- bounded continuation instructions: worksheet title, exact grounded question, source page number, and exact answer paragraphs.

It has no field capable of carrying a path, URL, HTML, command, renderer class, credential, or font selection outside the single allowlisted ID. The API client never constructs this contract. The adapter creates it from the committed domain projection and stored server evidence. The parent hashes the contract before launch and checks it after the worker and again after validation, preventing a renderer or validator from changing its own authority.

## OpenPDF preservation path

- OpenPDF is pinned to 3.0.5.
- `PdfReader.isRebuilt()` is an explicit `unsupported_rebuilt_xref` rejection.
- `PdfStamper(..., append=true)` is the only source-manipulation mode.
- automatic rotated-content adjustment is disabled; Claros's integer milli-point transform is applied explicitly.
- non-RTL generated text uses Noto Sans, Identity-H, embedding, and `setGlyphSubstitutionEnabled(false)`.
- continuation pages use OpenPDF layout with the same glyph-substitution setting and visible question/source/page identifiers.
- the worker has no HTML or external-resource resolver.
- any RTL bidi class is rejected before launch and checked again by Java.

The prior RTL PARTIAL result concerns generated-text shaping/extraction certification. Arabic and Hebrew source preservation, physical placement, qpdf validity, and PDF.js rendering did not fail in the hostile harness; Arabic PDF.js extraction used presentation forms, and neither script received linguistic shaping certification. This spike therefore fails RTL closed even though no source-preservation or coordinate loss was observed.

## Independent validation gate

OpenPDF does not validate itself. The release supervisor requires:

1. qpdf structural check with a zero exit code; warnings are not converted to success.
2. PDFBox reopen and low-DPI render of every page.
3. PDFBox exact extraction of each inline string from derivative-only page content streams. This specifically detects the `office -> ofce` ToUnicode regression.
4. PDFBox exact ordered-token extraction for continuation answers plus question identity, source question, page ordering, and page numbering.
5. PDFBox text-position coordinates within 1.25 physical points of every approved baseline.
6. page count, all five page boxes, rotation, and UserUnit.
7. exact retention of every decoded source content stream.
8. semantic equality of source-page annotations/links, AcroForms, outlines, document information, XMP, encryption/permissions, with containment of source image and embedded-font hashes.
9. PDF.js exact generated-text checks and canvas rendering of every page.
10. output byte limit plus source, contract, and output hashes rechecked immediately before release.

Byte equality is intentionally not required. Incremental serialization is allowed to add objects, but source objects and covered semantics must remain.

## Local security-control status

`ENFORCED` means exercised by running code/tests on this host. `SIMULATED` means code/layout follows the intended restriction but the host OS did not independently confine it. `UNVERIFIED` means only a deployment specification or provider capability was inspected.

| Control | Status | Evidence / limitation |
|---|---|---|
| Dedicated OpenPDF process | ENFORCED | One JVM per render; active PID tracked and reaped. |
| No inbound network to OpenPDF | ENFORCED | Worker is a file-contract CLI and opens no listener. PDF.js's loopback server belongs to the independent validator. |
| Non-root worker identity | UNVERIFIED | Dockerfile declares UID/GID 10001; Docker daemon was unavailable. |
| No outbound network | UNVERIFIED | No worker fetch code/URL field exists; host networking was not blocked. Docker launcher declares `--network none`. |
| Read-only runtime filesystem | UNVERIFIED | Docker launcher declares `--read-only`; host process retains the developer account's ambient filesystem access. |
| Read-only font directory | SIMULATED | Closed ID plus checksum is enforced and worker only opens the font for reading; host ACL was not a sandbox boundary. |
| Per-job writable directory | SIMULATED | All intended writes are under a server-created directory; host ACL does not prohibit other writes. |
| Server-created opaque job path | ENFORCED | `tempfile.mkdtemp`; path never appears in caller contract. |
| Fixed checksum-pinned font | ENFORCED | Python and Java verify the same SHA-256. |
| No arbitrary HTML/URL/resource resolution | ENFORCED | Strict schema plus no such worker code path. |
| Input byte limit before PDF parse | ENFORCED | Parent rejects first; Java rechecks file size. |
| Discovered page-count limit | ENFORCED | Java checks `PdfReader.getNumberOfPages`; parent checks stored evidence. |
| Output byte limit | ENFORCED | Counting output stream aborts OpenPDF as it crosses the bound; parent rechecks. |
| Temporary-storage limit | SIMULATED | Output is bounded and cleanup is enforced; host supplied no per-directory quota. Docker tmpfs specifies 96 MiB but was not run. |
| JVM heap limit | ENFORCED | `-Xmx`; a 96 MiB allocation under `-Xmx32m` terminated non-zero. |
| CPU limit | UNVERIFIED | Docker launcher requests one CPU; no host cgroup/job-object boundary was available. |
| Wall-clock deadline | ENFORCED | Supervisor kills/reaps the active process; timeout tests pass. |
| Process/thread limit | UNVERIFIED | Docker launcher specifies PID 64; host run did not enforce it. |
| Kill entire OpenPDF worker on timeout | ENFORCED | The real worker is a single JVM; POSIX uses a process-group kill and Windows kills that JVM. |
| Quarantine before release | ENFORCED | Parent cannot read derivative bytes until all validators pass. |
| Cleanup on every outcome | ENFORCED | Read-only job copies are made deletable only during final cleanup; success and every injected failure leave no job directory. |
| Privacy-safe logs/status | ENFORCED | Child stdout/stderr are discarded; status files contain only IDs, hashes, sizes, counts, timings, and bounded error codes. |

## Smallest viable production topology

The current repository deploys one Python 3.11 Cloud Run service with 2 vCPU, 2 GiB, concurrency 4, and GCS; Java is absent. A same-container child JVM would preserve process killability but would not establish no-network or filesystem confinement from the API. A same-instance Cloud Run sidecar is also insufficient for the desired network boundary because sidecars share an instance network namespace and communicate over localhost ([Cloud Run sidecars](https://docs.cloud.google.com/run/docs/deploying#sidecars)).

The smallest credible topology is one additional stateless, private PDF-pipeline Cloud Run service:

- Claros API remains the sole owner of assignment state and immutable object publication.
- The API sends the strict job plus source bytes over authenticated service-to-service HTTPS. The worker service accepts only the API service account and internal ingress ([service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service), [ingress controls](https://docs.cloud.google.com/run/docs/securing/ingress)).
- A supervisor in that service launches OpenPDF and independent validators as separate processes, stores quarantine only in per-request temporary space, and returns bytes only after the gate.
- The worker service account receives no GCS or general application credentials. Encrypted PDFs remain unsupported, so no PDF password is transported or logged.
- Set service concurrency to 1 initially; set container CPU/memory and request deadline; kill/recycle the instance after resource-limit breaches. Cloud Run enforces configured CPU/RAM with cgroups and terminates over-memory instances ([runtime contract](https://docs.cloud.google.com/run/docs/container-contract)).
- Route all egress through a dedicated VPC and deny it with firewall policy; Cloud Run otherwise permits public-internet egress by default ([Cloud Run egress controls](https://docs.cloud.google.com/run/docs/securing/security#egress)).
- Expose only a health/startup probe and authenticated render endpoint. Log bounded IDs/hashes/metrics/error codes only.

This adds a service and direct IPC but not a queue or a second assignment authority, so it is compatible with the repository's synchronous P0 ownership decision. Cloud Run local writes count against memory and require explicit cleanup ([memory limits](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits)); the per-job byte budget must therefore cover source, derivative, status, and validator working data.

The complete validator runtime needs Java/PDFBox, qpdf, Node, Playwright, and Chromium. The shaded Java artifact measured 18,431,871 bytes, but the full container image size and cold start are unverified because Docker could not run locally.
