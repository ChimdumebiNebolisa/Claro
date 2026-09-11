# Claros V2 Architecture and Delivery Decisions

- **Status:** Accepted for Gate 0
- **Recorded:** 2026-09-04
- **Change:** `claros-reconstruction`

These decisions freeze the interfaces needed to begin Gate 1. Later changes
require evidence, an entry here, and the applicable OpenSpec update before
implementation.

## Product and migration

### D-001 — Authority and branch

Use the V2 authority order in `BASELINE_AUDIT.md`. Work on
`codex/claros-v2-nerdy` from `5fb2177`; do not implement V2 directly on
`main` and do not restore a historical branch wholesale.

The three authority files remain byte-identical, including their intentional
Markdown hard-break spaces. Their SHA-256 values are the integrity check;
`git diff --check` applies to authored files with those three verbatim imports
excluded when inspecting the Gate 0 commit.

### D-002 — OpenSpec strategy

Update `openspec/changes/claros-reconstruction` in place. Rewrite
`worksheet-contract`, `answer-integrity`, `student-workspace`, and
`safe-export`; add `document-understanding`, `deterministic-placement`,
`assignment-lifecycle`, and `voice-guidance`. The previous 17/19 task record is
V1 disposition history and contributes zero V2 completion credit.

### D-003 — Cutover boundary

During Gates 1–5, V1 remains available at `/legacy` with `/api/v1`. V2 owns
`/app` and `/api/v2`. Remove the legacy route, server, styles, and dependencies
only after Gate 6 proves replacement behavior and captures migration evidence.

### D-004 — P0 boundary

P0 is the exact worksheet-to-approved-PDF loop. Same-browser reload through a
signed session is included because production truth must survive instance
replacement. Cross-device/shareable resume, OCR, accounts, educator features,
multiple choice, complex tables/math, manual placement, and arbitrary PDF
support remain P1 or deferred.

## Public routes, API, and ownership

### D-005 — Routes

Final routes are:

```text
/                                                marketing
/app                                             upload/check/ready
/app/:assignmentId                               active question
/app/:assignmentId/review                        worksheet review
/app/:assignmentId/export/:exportId               export result
/legacy                                           migration-only V1
```

FastAPI supplies an SPA fallback for these non-API routes and `/health` for
Cloud Run. API and unknown asset paths never fall through to the landing page.

### D-006 — `/api/v2` contract

Implement assignment creation/status, Range-capable authorized source
streaming, page context, candidate creation, rephrase, exact review,
confirmation, answer revision, idempotent export creation/status/download, and
Realtime client-secret issuance. FastAPI OpenAPI is the transport authority;
generate TypeScript types plus a thin `openapi-fetch` client and fail CI on
drift.

Every mutation includes `assignment_version`. Responses return the effective
version and `ETag`. Errors use:

```json
{
  "error": {
    "code": "stable_code",
    "message": "student-safe text",
    "recoverable": true
  }
}
```

### D-007 — State ownership

- XState owns visible workflow and recoverable product states.
- TanStack Query owns server reads/mutations, cancellation, retry, and cache
  invalidation.
- The Realtime adapter owns media/connection/transcript/model events.
- Local component state owns only disclosure, focus, dialog/menu visibility,
  and non-authoritative animation.
- FastAPI plus persisted manifests own assignment, candidate, confirmation,
  placement, and export truth.

### D-008 — Candidate and confirmation integrity

Candidate origins are exactly `student_verbatim`, `student_normalized`,
`claros_rephrase`, `student_after_guidance`, and `student_edited`. The server
derives or validates origin from the interaction path; clients cannot assert
arbitrary provenance. The UI exposes only **Your words** and **Suggested
wording**.

A review token lives for 10 minutes and binds owner, assignment, question,
candidate ID/version, exact-text hash, placement hash, and assignment version.
The first confirmation mutates once; an exact request replay returns the
original result, while altered, expired, stale, or conflicting requests fail.
A revision keeps the last confirmed answer exportable until a replacement is
confirmed and invalidates all prior review tokens.

## Frontend and design system

### D-009 — Visible component foundation

Untitled UI React v8 is the sole visible V2 foundation. Install through the
official CLI with `--lib-version 8`, inspect every generated diff, and vendor
only these confirmed free components:

```text
file-upload-base
modal
loading-indicator
empty-state
textarea
radio-buttons
badges
```

Use existing Untitled primitives to compose Claros-specific notices and cards.
Use `@untitledui/icons` for ordinary icons. Do not add another component kit or
handcraft ordinary controls.

### D-010 — PDF rendering

Pin the EmbedPDF family to one `2.15.0` version. Use
`@embedpdf/react-pdf-viewer` for the lazy full-document dialog and the
headless render plugin’s `renderPageRect` for authentic, backend-authorized
context crops. Disable annotation, form, redaction, print, export, capture,
open, and close capabilities that bypass Claros. The landing route and direct
typed path must not load PDF/Realtime code prematurely.

### D-011 — Layout and visual constants

- Desktop: 64px top bar, task-first DOM order, task content up to 760px, fixed
  400–440px source pane, no resizer.
- Tablet: task first, source card below, full PDF in a dialog/route.
- Mobile: single column, sticky compact progress, task first, full-screen PDF
  dialog, stacked wording cards.
- Inter is the application font. Use 32px desktop and 28px mobile question
  text, 16px body text, and at least 13px supporting text.
- Use the authority colors, an 8px rhythm, 10–12px controls, 14–18px workflow
  cards, and 20–24px major shells.
- Motion is limited to voice state, answer placement, question progress, and
  the supplied mobile-dialog transition; reduced motion updates immediately
  and announces the result.

### D-012 — Exact review and audio

The review state uses the execution PRD’s exact strings, including **Use this
exact answer**. **Hear it** is functional on demand in P0, but playback success
does not gate button/keyboard confirmation. Automatic read-before-confirm is
P1. Casual agreement is ignored in every state.

## Backend, persistence, and document engine

### D-013 — Service and request lifecycle

Use one Python 3.11 FastAPI service on Cloud Run. It serves `/api/v2`, `/health`,
and the Vite production assets. Upload analysis and export are bounded,
synchronous P0 requests with truthful indeterminate UI. Status endpoints remain
reload-safe and permit later async evolution. Do not use FastAPI background
tasks, a second service, or a queue as the sole owner of assignment truth.

### D-014 — Storage and anonymous ownership

Production uses private GCS; development/tests use a filesystem adapter.
Production startup fails on local or in-memory storage. Store immutable source,
physical IR, previews, exports, and export manifests; update the assignment
manifest with GCS generation-match CAS. Use a signed `HttpOnly`, `SameSite=Lax`
owner cookie, set `Secure` in production HTTPS, and enforce origin checks for
mutations. No bearer secret is stored in browser storage.

Anonymous assignments have a 24-hour absolute logical TTL. Authorization fails
immediately after logical expiry; GCS lifecycle deletion is best-effort and is
not presented as an exact deletion guarantee.

### D-015 — Physical IR

Canonical coordinates are crop-box-relative top-left integer milli-points.
Each page records media/crop boxes, rotation, user unit, and the affine
transform. Blocks record stable SHA-256-derived IDs, exact UTF-8 text, kind
(`text`, `line`, `rect`, `form_field`, `image`), bounding box, reading order,
`join_after` (`none`, `space`, or `newline`), and ambiguity flags. The renderer
alone converts to the PDF/ReportLab bottom-left system through tested affine
transforms.

### D-016 — Document pipeline and placement

Use pikepdf preflight/normalization, pdfplumber extraction, strict block-ID
semantic mapping, deterministic geometry, ReportLab overlays/appendices, pypdf
source-page cloning/assembly, then pikepdf validation. Geometry priority is
writable form field, safe rectangle, answer-line group, bounded whitespace,
then appendix. A non-identity rotation/crop transform is appendix-only in P0
unless the gold corpus proves it end to end.

### D-017 — Text fitting and export

Vendor Noto Sans Regular/Bold and the OFL license. Preserve word boundaries and
explicit newlines; fit from 12pt to a 10pt floor with 1.2 leading, padding, and
collision checks. Failure to fit routes to appendix; an unsupported glyph is
an explicit pre-confirmation/export error. The appendix may span pages and
contains the exact question, page, stable identifier, and approved answer; it
needs no source-page marker in P0.

Export clones immutable source pages, renders only confirmed text, appends
answer pages, validates source generation/hash, evidence, text, bounds, page
count, and openability, and uploads an immutable version-derived export object.

## OpenAI, privacy, and deployment

### D-018 — Semantic mapping and rephrase

Responses calls use strict structured output, `store: false`, and no tools.
Worksheet text is untrusted data. The semantic model can select only provided
block IDs; the server rejects unknown, duplicate, overlapping, reordered,
ambiguous, or malformed results and reconstructs exact question text locally.
Rephrasing is separate, preserves the original candidate, and fails when
postvalidation detects a new unsupported factual claim.

Benchmark `gpt-5.6-luna`, then `gpt-5.6-terra`, then `gpt-5.6-sol`; select the
first candidate with 100% required-gold correctness, zero invalid IDs over
three runs, and acceptable recorded p95 latency. Record the selected model in
this file after Gate 4 rather than choosing by preference.

### D-019 — Realtime

Use `@openai/agents/realtime` over WebRTC with
`OPENAI_REALTIME_MODEL=gpt-realtime-2.1`. A short-lived credential is issued
only after assignment/question/mode/version validation. Both typed and voice
turns enter the same adapter/candidate boundary. Realtime may fetch context,
set a candidate, request rephrase, enter review, or report a voice issue; it
cannot approve, select coordinates, mutate a PDF, or export. One bounded
automatic reconnect is permitted; failure preserves state and exposes
**Retry voice** and **Continue by typing**.

### D-020 — Privacy and production defaults

Operational logs contain no raw PDF/question/answer text, audio, transcripts,
provider payloads, API keys, review tokens, or session secrets. Persist only
bounded conversation text required for the student’s active task; never store
raw audio. Rate-limit analysis and Realtime secret issuance. Use `/health`
rather than `/healthz`, which historical Cloud Run deployment evidence shows
can be intercepted.

Initial Cloud Run settings are 2 CPU, 2 GiB memory, concurrency 4, 300-second
timeout, minimum 1 and maximum 1 instance. The one-instance ceiling is required
while rate limiting is process-local. Multiple instances require a shared or
edge limiter plus recorded staging evidence; load and cost measurements alone
cannot waive that security boundary.

### D-021 — Gate 1 frontend runtime and toolchain result

The frontend declares Node `>=22.12 <23`; the clean Gate 1 evidence run used
Node `v22.23.2`. Every direct npm dependency is exact-pinned and the lockfile
freezes transitives. ESLint remains on exact `9.39.4` because the selected JSX
accessibility plugin does not accept ESLint 10; this is a compatibility choice,
not permission for floating dependencies.

The official Untitled CLI `0.1.64` was run with library version 8. Only the
seven approved primitives in D-009 and their required local foundations were
accepted. `@openai/agents` remains absent until Gate 5. React strict-mode double
mounting is not enabled at the application root because pinned EmbedPDF 2.15.0
duplicates its document registry during the development-only mount/unmount
probe; deterministic unit, Storybook, and fresh-server browser tests instead
exercise teardown and remount behavior.

Development CSP permits inline React Refresh code while production does not.
Both permit `wasm-unsafe-eval` and blob workers required by PDFium. Production
browser smoke, rather than configuration inspection alone, is the acceptance
test for this exception.

### D-022 — Pinned EmbedPDF accessibility boundary

EmbedPDF 2.15.0 renders the authentic source in a shadow root. Claros applies a
small adapter repair for observed vendor markup: decorative raster layers have
empty alt text, decorative button SVGs are hidden from the accessibility tree,
and the page-scroll viewport is a named, keyboard-focusable region. The adapter
does not label worksheet content or alter document bytes. Because the repair
uses a pinned vendor class, any EmbedPDF upgrade is blocked until Storybook axe,
keyboard/screen-reader inspection, Range loading, and the production
CSP/WASM/worker flow are rerun.

### D-023 — Gate 3 transport contract freeze

FastAPI OpenAPI uses `snake_case`; generated browser types adapt into the
existing product-domain types rather than redefining them. The sole mutation
without `assignment_version` is initial `POST /api/v2/assignments`, because no
assignment exists yet. It accepts multipart form data containing exactly one of
`file` or `sample_id`. Every other mutation requires `assignment_version`, and
every JSON success returns the effective `version` with an ETag formatted as
`"assignment-version-{version}"`.

The V2 endpoint inventory is assignment create/status, authorized `GET`/`HEAD`
source streaming, page context, candidate creation, optional rephrase, review
issuance, confirmation, begin revision, export create/status/download, and
Realtime client-secret issuance. Cross-owner access at every nested endpoint
returns the same `404 assignment_not_found` response as a nonexistent object.
FastAPI validation errors are converted to the stable Claros error envelope;
they never expose Pydantic internals or submitted worksheet/answer text.

Upload analysis remains synchronous in P0. The manifest is durably written as
`analyzing` during the request, then as `ready`; a bounded timeout or handled
failure writes `analysis_failed`. Page context requires `question_id` and may
request the confirmed derivative preview. Its display crop is a top-left
integer milli-point rectangle authorized by the server and is not placement
authority.

Candidate text is preserved exactly after UTF-8 validation and is limited to
8192 encoded bytes as a security/resource envelope. This limit never controls
placement. Beginning revision increments the assignment version, retains the
last confirmed answer, and returns a neutral edit seed; `student_edited` is
assigned only when the student submits changed text. Gate 3 exposes frozen
rephrase and Realtime schemas but returns a stable recoverable
`provider_unavailable` response until Gates 4 and 5 install their providers.

### D-024 — Gate 3 manifest, version, and idempotency freeze

Public assignment version increments once for candidate replacement, rephrase
creation or selection, first confirmation, and begin revision. Review issuance,
export creation/status, and Realtime credential issuance return the current
version without incrementing it. Internal manifest generation may still change
for these operations through storage CAS.

Review tokens are random opaque values; persistence stores only an HMAC digest
and bindings for owner, assignment, question, candidate ID/version, exact-text
hash, placement hash, assignment version, and expiry. A durable confirmation
receipt keyed by token digest plus request digest makes an exact replay return
the original confirmation after process replacement. Any changed, expired,
invalidated, or stale replay fails without mutation.

Storage exposes only immutable create, exact read/range read, generation-bound
compare-and-swap, and exact generation-bound delete. A manifest mutation loads
bytes plus generation, validates owner/expiry/version, applies one pure domain
operation, serializes deterministic UTF-8 JSON without ASCII escaping, and
writes against the observed generation. A lost generation precondition maps to
`assignment_version_conflict`; the service does not retry over newer state.
Failed request cleanup deletes only exact objects created by that request.

### D-025 — Gate 3 execution and placement outcome

The application request budget is 270 seconds beneath Cloud Run's 300-second
request timeout. Each operation retains a 10-percent recovery reserve, storage
and document phases receive shrinking deadlines, every GCS RPC has a five-second
timeout, and transient GCS operations retry only within an eight-second bounded
window. A handled analysis failure durably records `analysis_failed` and returns
the signed owner cookie needed to reload that state.

Deterministic placement algorithm `v2.0.1` evaluates candidates in the frozen
priority order but does not stop at an unsafe candidate. Collision, occupation,
or fit failure falls through to the next lower-priority class and ultimately to
appendix. It never relaxes bounds, collision, transform, 10pt, or exact-text
requirements to preserve an inline result.

Gate 3 production code is frozen at accepted clean checkpoint
`88cda664f55abf698a1d56567e814e024708ad0a`. The checkpoint contains no semantic
or Realtime provider implementation. Its rephrase and Realtime routes remain
the frozen, recoverable `provider_unavailable` boundary required before Gates 4
and 5.

### D-026 — Gate 3 remote-unblock decision

Passing local API, storage-contract, document, browser, audit, Terraform, and
manual PDF checks is necessary but does not substitute for production-container
and live revision-replacement evidence. A Windows Docker Desktop failure is a
bypassable local-environment problem and is not evidence against Cloud Run.
The authoritative container check is the dispatchable Ubuntu GitHub Actions job
for the exact commit: it builds the production Dockerfile, starts and restarts
the real FastAPI container, uploads a gold worksheet, exports and parser-reopens
completed PDFs, scans privacy-safe logs, and retains the logs/PDFs as workflow
artifacts.

Cloud Run, Artifact Registry, and private GCS remain the sole production
architecture. The demo is capped at one instance while rate limiting is
process-local. The accepted deployment proved live GCS persistence, Cloud Run
revision persistence, cross-owner denial, and that client-supplied
`X-Forwarded-For` values cannot choose a fresh limiter key. Gates 4 and 5 may
exist only as excluded draft trees until Gate 3 is recorded; they are not
integrated, committed, or counted as Gate 3 progress. Gate 3 tasks 3.8 and 3.9
are complete against the evidence in `artifacts/v2/gate3/verification.md`.

### D-027 — Gate 3 adopted-cloud and remote-build disposition

The owner-authorized target is the billed project `claro-490122`, region
`us-central1`, service `claros`, and private bucket
`claros-assignments-490122`. Existing Cloud Run, GCS, Artifact Registry,
runtime/deployment identities, and GitHub WIF resources are imported into the
dedicated remote Terraform state rather than duplicated. Claros is not moved to
Vercel; Cloud Run plus private GCS remains the production boundary.

GitHub's Ubuntu runner is the authoritative production-container acceptance
environment. Google Cloud Build is the supported remote source-build path and
uses a clean committed archive plus the digest-pinned BuildKit configuration in
`deploy/cloudbuild.yaml`. The final image digest is promoted to Cloud Run
without requiring Docker Desktop.

Safe adoption does not silently change existing data-retention or deployment
access. The one-day bucket lifecycle and soft-delete-disable proposal remains
unapplied because it is data-affecting; the application still enforces 24-hour
logical expiry immediately. Legacy project-level grants on the adopted deploy
identity are removed only after the owner-gated Gate 6 WIF deployment proof.
These two follow-ups are recorded risks, not missing Gate 3 durability
evidence.

The Gate 0–3 feature history was re-baselined into one clean pull-request
commit after three secret-like synthetic test values were replaced. The clean
checkpoint has the exact tracked tree of the verified pre-scrub head, and both
GitGuardian and the Ubuntu container workflow pass on the re-baselined pull
request without weakening secret detection.

### D-028 — OpenPDF renderer promotion without production activation

The owner-directed 2026-09-11 migration supersedes D-016 and D-017 only for
the export rendering and final validation implementation. Python continues to
own preflight, physical IR, question grounding, deterministic fitting, placement
hashes, immutable object publication, and application state. The selected
OpenPDF path replaces ReportLab/pypdf rendering with a strict Java 21 child
process using OpenPDF 3.0.5, Apache FOP 2.11, PDFBox 3.0.8, Jackson 2.20.0, and
the existing allowlisted Noto Sans Regular font.

`CLAROS_PDF_ENGINE` accepts only `current` or `openpdf`. Selection is made once
at application construction; selecting OpenPDF verifies Java 21+, the shaded
worker JAR, the font checksum, and qpdf before serving requests. There is no
automatic fallback. `current` remains the configuration and Cloud Run template
default because this work does not authorize a deployment or production
activation.

OpenPDF output is quarantined and cannot reach storage until qpdf succeeds and
the independent PDFBox process proves generated text, source preservation,
placement evidence, page counts, and renderability. Worker crashes, deadline
expiry, malformed status, output bounds, or either validator failure delete the
job directory, preserve confirmed answers, and publish nothing. PDF.js remains
a CI/release compatibility renderer and is intentionally absent from the
synchronous application request.

## Dependency plan

The lead alone edits dependency manifests and lockfiles. Pin current compatible
versions and retain a single lockfile per ecosystem.

### Add in Gate 1

| Purpose                | Packages                                                                                                                                                                                  |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Untitled foundation    | `@untitledui/icons`, `react-aria-components`, `tailwindcss-react-aria-components`, `tailwindcss-animate`; vendored Untitled UI v8 source                                                  |
| PDF rendering          | `@embedpdf/react-pdf-viewer`, `@embedpdf/core`, `@embedpdf/engines`, `@embedpdf/pdfium`, `@embedpdf/models`, `@embedpdf/plugin-document-manager`, `@embedpdf/plugin-render`, all `2.15.0` |
| Server/workflow state  | `@tanstack/react-query`, `openapi-fetch`                                                                                                                                                  |
| Bounded animation      | `motion`                                                                                                                                                                                  |
| Deterministic UI tests | `msw`, `msw-storybook-addon`, Testing Library, `user-event`, `jsdom`, Storybook/Vitest browser integration                                                                                |
| Generated API          | `openapi-typescript` as a development dependency                                                                                                                                          |
| Quality                | ESLint flat config, TypeScript ESLint, React Hooks, JSX accessibility plugins                                                                                                             |

Retain the current compatible React 19 and TypeScript lines unless the reviewed
vendored Untitled source demonstrates a concrete incompatibility. Preserve
XState, Zod 4, React Router, Vite, Tailwind, Inter, Storybook, Vitest,
Playwright/axe, `clsx`, and `tailwind-merge`; avoid unrelated framework
upgrades during the foundation gate.

### Add in Gate 5

Add `@openai/agents` for its `@openai/agents/realtime` browser entry point only
when the Gate 5 voice adapter is implemented. Keeping it out of Gate 1 makes
the no-Realtime direct typed bundle boundary observable and avoids an unused
runtime dependency.

### Add in Gate 3

Runtime Python dependencies: FastAPI, Uvicorn, Pydantic Settings,
`python-multipart`, `itsdangerous`, Google Cloud Storage, pikepdf, pdfplumber,
ReportLab, pypdf, and the OpenAI Python client. The maintained alternative
exporter adds a Java 21 shaded worker with OpenPDF/PDFBox dependencies plus a
separate qpdf executable; it reuses the vendored Noto Sans font. Development dependencies:
pytest, pytest-asyncio, HTTPX, coverage, Ruff, and pip-audit. Use pinned
`requirements-server.txt` and `requirements-dev.txt` plus `pyproject.toml`
tool configuration, matching the repository’s historical packaging approach.

### Retain temporarily, then remove

Keep `radix-ui`, `react-pdf`, `react-dropzone`,
`react-resizable-panels`, `lucide-react`, `tw-animate-css`, and the Node server
only while `/legacy` imports them. Gate 6 removes each dependency after import
and production-bundle evidence proves it is unused. Do not add PyMuPDF or any
second visible component system.

Before finalizing locks, verify the installed EmbedPDF tarball licenses, retain
font licenses, run `npm audit --audit-level=high` and `pip-audit`, and record any
exception in `RISKS.md`. The Untitled CLI has search/install side effects, so
run it only on the V2 branch and review its entire diff before acceptance.

## Gate 1 ownership

| Owner                      | Exclusive write scope                                                                                                             |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Lead                       | Dependency manifests/locks; routing; providers; semantic tokens; XState/domain contracts; API/OpenAPI types; shared configuration |
| Untitled integrator        | Vendored base components selected in D-009, after lead freezes dependency/theme paths                                             |
| Document-viewer integrator | EmbedPDF adapter and its isolated tests, after lead freezes source/context interfaces                                             |
| Feature-screen integrator  | Feature presentation and stories against frozen fixtures; no shared contracts or tokens                                           |
| Review agents              | Read-only evidence, contract, accessibility, security, and visual review                                                          |

Implementation scopes must remain disjoint. A requested cross-boundary change
returns to the lead before either agent edits it.
