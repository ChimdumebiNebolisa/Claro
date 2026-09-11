## Context

The current branch is a verified V1 vertical slice: React/Vite/TypeScript,
Radix-oriented UI, `react-pdf`, XState, and a Node `/api/v1` service whose
assignment data is process-local and whose upload path accepts one known sample.
It demonstrates exact review and server-owned placement tokens, but it cannot
satisfy the V2 document, persistence, voice, accessibility, or deployment
contract.

The controlling sources, in descending order, are the V2 execution PRD, V2
product contract, V2 design authority, accepted tests/evaluation thresholds,
current implementation, and git history. This order resolves stale statements
in the lower authorities: Untitled UI React and EmbedPDF control V2 even where
the product/design documents still mention Radix or React-PDF. Historical code
is a source of tested invariants, never a branch to restore wholesale.

The delivery deadline is 2026-09-18. Gates are cumulative: a later gate cannot
waive an earlier product, PDF-integrity, accessibility, security, or evidence
requirement. Production code does not begin until Gate 0 is recorded as passed.

## Goals / Non-Goals

**Goals:**

- Deliver one complete question-grounding, direct/guided answer, exact-review,
  deterministic-placement, and derivative-export loop.
- Make source evidence, approval, geometry, and export authority server-owned
  while keeping the visible workflow accessible and recoverable.
- Preserve the original PDF and exact confirmed Unicode answer while choosing
  inline or attached-page placement deterministically.
- Keep runtime truth durable across Cloud Run instance replacement and expose a
  generated, versioned API contract to the browser.
- Make every high-risk claim observable through corpus, contract, browser,
  accessibility, visual, security, and deployed smoke evidence.

**Non-Goals:**

- OCR, scanned worksheets, multiple choice, drawing, arbitrary math/table
  layout, grading, teacher/classroom workflows, accounts, billing, LMS
  integration, collaboration, or universal PDF compatibility.
- Model-generated geometry, client-edited coordinates, drag-to-place, or
  indefinite font shrinking.
- Cross-device/shareable anonymous resume, background workers, multiple
  services, or other P1 work before all P0 gates pass.
- Retaining either product generation permanently after the Gate 6 cutover.

## Decisions

### 1. Rebaseline the existing change and migrate behind `/legacy`

Continue `claros-reconstruction` because there are no archived base specs and a
second change would duplicate eight new capabilities without a valid delta
relationship. Preserve the previous 17/19 checklist as historical disposition,
then start a distinct unchecked V2 Gate 0–7 task graph.

Create `codex/claros-v2-nerdy` from the audited baseline commit. V2 owns `/`,
`/app`, `/app/:assignmentId`, `/app/:assignmentId/review`, and
`/app/:assignmentId/export/:exportId`; V1 is frozen at `/legacy` until Gate 6.
The old `/api/v1` service remains only as migration evidence and is removed with
its unused dependencies after V2 passes. A wholesale historical restore was
rejected because it would reintroduce Gemini, PyMuPDF, OCR, teacher, and manual
placement scope that conflicts with P0.

### 2. Use one V2 visual foundation and load expensive capabilities on demand

Use React 19, Vite, TypeScript, Tailwind, XState, and Storybook from the current
foundation. Add Untitled UI React v8 as the sole visible V2 primitive layer,
with its React Aria behavior preserved, and install only the confirmed free
components needed by the screens. Claros-specific cards, notices, document
overlays, and voice meters compose those primitives. Legacy CSS is scoped under
the legacy route root so it cannot alter V2 focus or control behavior.

Use EmbedPDF packages pinned to one version for both authentic source rendering
and controlled page-region crops. The full viewer is read-only and disables
annotation, forms, redaction, print, export, capture, document-open, and
document-close controls. A headless `renderPageRect` adapter renders only a
backend-authorized region; the browser never selects or changes placement.
Marketing loads neither PDF nor Realtime code, and direct typed answering loads
neither Realtime nor its audio dependencies.

The desktop shell has a 64px header, a primary task column capped near 760px,
and a fixed 400–440px source pane. Tablet stacks source after task. Mobile puts
task first in DOM order and opens the worksheet in a full-screen modal. There is
no resizer or 50/50 editor split. Application type is Inter at a 16px body
target, 32px desktop/28px mobile question target, and 13px minimum supporting
text. Motion is limited to voice state, placement, question progression, and
the mobile sheet, with an immediate announced reduced-motion result.

### 3. Separate visible workflow, server state, transport, and disclosure state

XState owns upload/check/readiness, active question, equal path selection,
direct/guided substates, comparison, exact review, confirmation, answer-added,
worksheet review, and export/error states. TanStack Query owns all `/api/v2`
fetches/mutations and cache invalidation. The Realtime adapter owns WebRTC,
tracks, captions, turns, interruptions, and reconnect. Local React state owns
only focus-neutral disclosure and animation details.

The direct transcript and editor are one candidate source, not parallel truths.
Guided transcript turns never become the final candidate automatically. Both
paths converge on the same review and confirmation mutations. MSW and a fake
Realtime adapter exercise every state before live providers are connected.

### 4. Make FastAPI OpenAPI the transport authority

Build one Python 3.11 FastAPI service under `/api/v2`; it serves the production
Vite assets and excludes `/api` and `/health` from SPA fallback. `/health` is
the Cloud Run probe because repository history shows `/healthz` can be
intercepted in that environment.

The API covers assignment creation/status, Range-capable authorized source
streaming, page context, candidate creation, optional rephrasing, review,
confirmation, revision, idempotent export/status/download, and Realtime client
credentials. Upload analysis and export remain bounded synchronous operations
in P0; status resources make reload and future async work safe. FastAPI OpenAPI
generates TypeScript types and an `openapi-fetch` client; CI rejects schema
drift. The stable error shape is
`{ "error": { "code": string, "message": string, "recoverable": boolean } }`.

Every mutation supplies `assignment_version`, and every state response returns
the updated version and `ETag`. A version mismatch returns a stable conflict
without overwriting newer state. Expensive analysis and Realtime-secret routes
are rate-limited.

Candidate input includes exact text and interaction evidence; the server
derives or validates origin rather than accepting arbitrary provenance. Review
returns a snapshot and token bound to owner, assignment, question, candidate ID
and version, exact-text hash, placement hash, assignment version, and a 10-minute
expiry. The first confirmation changes state once. An identical retry returns
the original result; altered, stale, expired, or cross-boundary use fails.

### 5. Persist anonymous ownership and immutable artifacts in GCS

Issue a signed `HttpOnly`, `SameSite=Lax` owner cookie and add `Secure` in the
production HTTPS environment. Store an owner hash in the manifest rather than
a browser bearer secret. Require same-origin mutation requests and enforce
owner binding on every assignment object.
Same-browser reload restoration is P0; shareable or cross-device access is P1.

Production uses private GCS objects:

```text
assignments/{assignment_id}/source/original.pdf
assignments/{assignment_id}/analysis/physical-ir.json
assignments/{assignment_id}/manifest/assignment.json
assignments/{assignment_id}/previews/page-{page_number}.png
assignments/{assignment_id}/exports/{export_id}/completed.pdf
assignments/{assignment_id}/exports/{export_id}/manifest.json
```

Create source, IR, and exports with `if_generation_match=0`; update manifests by
generation-aware compare-and-swap. Export IDs derive from assignment version so
the same version is idempotent. A local filesystem adapter supports development
and tests, but production startup fails when configured for local or in-memory
storage. Anonymous assignments have a 24-hour absolute logical TTL; access
stops at expiry and GCS lifecycle cleanup is best-effort.

Operational logs contain bounded identifiers, stages, timing, and error codes,
never raw PDF/question/answer text, audio, transcript, provider payload,
credentials, review tokens, or cookies. Raw audio is never stored.

### 6. Keep physical truth deterministic and semantic output closed-world

Preflight uses pikepdf to enforce a valid readable PDF, content-based type,
10 MiB byte limit, 1–8 pages, no encryption/password requirement, selectable
text, supported rotations/crop boxes, and bounded extracted text. pdfplumber
emits canonical physical IR containing source hash, media/crop boxes, rotation,
user unit, affine transform, exact UTF-8 text, stable reading order, and blocks
of kind `text`, `line`, `rect`, `form_field`, or `image`.

Canonical display coordinates are crop-relative top-left integer milli-points.
Stable block IDs derive from document/page/type/order/content/box evidence.
Text blocks carry explicit `join_after: none|space|newline`; exact question text
is reconstructed by code from selected blocks in physical order. Rendering
adapters alone convert canonical geometry into renderer-specific PDF
bottom-left coordinates through tested affine transforms.

OpenAI Responses receives stable IDs, exact text, kind, page, order, and bounded
deterministic relation hints. It returns strict structured question mappings
containing existing block IDs and semantic warnings, never coordinates.
Post-validation rejects unknown/duplicate/overlapping/reordered IDs,
unsupported types, unsafe ambiguity, and failed exact reconstruction. Calls use
`store: false`, no tools, and treat worksheet text as untrusted data.

Benchmark semantic models in the order `gpt-5.6-luna`, `gpt-5.6-terra`, then
`gpt-5.6-sol`. Select the first with 100% required-gold correctness, zero
invalid IDs across three runs, and acceptable recorded p95 latency; keep the
result environment-configurable. Recorded responses drive deterministic CI.

### 7. Resolve placement and export without changing student text

Geometry priority is safe writable form field, rectangular answer box,
answer-line group, bounded whitespace, then attached answer page. Outcomes are
`inline`, `appendix`, or `reject`; lack of inline space selects `appendix`, not
`reject`. Ambiguous competing regions also select the appendix when the
question is grounded. Non-identity rotation/crop transforms are appendix-only
in P0 until the gold corpus proves their complete affine path.

Use vendored Noto Sans Regular/Bold with its OFL license. Fit exact approved
Unicode at 12pt down to a 10pt floor, wrapping at word boundaries with 1.2
leading, padding, bounds, and collision checks. Run fit on a scratch surface
before authorizing review. Overflow routes to appendix; unsupported glyphs
fail before confirmation. Never truncate, normalize, paraphrase, white out, or
overwrite source content.

Export reloads the immutable source generation, current confirmed answers, and
their evidence and revalidates every hash and placement before invoking the
selected renderer. `CLAROS_PDF_ENGINE=current|openpdf` is explicit; `current`
remains the deployment default until a separately authorized production
selection. Selecting `openpdf` verifies Java 21+, the shaded worker JAR, the
allowlisted Noto Sans font, and qpdf during application startup. Missing
dependencies fail startup, and there is no silent renderer fallback.

The OpenPDF renderer runs as a bounded child process, incrementally stamps
validated inline lines onto immutable source pages, and appends paginated answer
pages. Its strict versioned contract contains only server-derived source,
physical-IR, exact-text, placement, font, and resource-limit evidence. Output
remains quarantined until qpdf structural validation and an independent PDFBox
validator prove page rendering, source preservation, placements, and generated
text. PDF.js renders and extracts a representative output in the CI/release
compatibility job only; it is not on the synchronous publication path. Each
appendix entry contains worksheet title, question number/stable ID, exact source
question, source page, and exact answer. Any worker, timeout, validator, or
resource failure preserves confirmed state and publishes no derivative.

### 8. Constrain Realtime to assistance, never authority

Use `@openai/agents/realtime` with WebRTC and `gpt-realtime-2.1`. FastAPI issues
a short-lived credential only after validating owner, assignment, active
question, mode, and version. Direct mode captures the student's words with
minimal interruption; guided mode asks one focused grounded question at a time
and requires the student to state a final answer.

Permitted actions can fetch active context, set a student-derived candidate,
request clearer wording, enter exact review, and report a voice issue. Voice
cannot choose geometry, approve for the student, export, rewrite source, or
write a PDF. The exact phrase `Use this exact answer` may invoke the same
authenticated confirmation endpoint only while exact review is active; casual
agreement is ignored.

Expose Ready, Listening, Thinking, Speaking, Interrupted, Connection lost, and
Microphone unavailable as text. Provide captions, stop, interrupt, mute, retry,
and typing. On failure preserve candidate and bounded relevant turns, make one
automatic reconnect attempt, and keep typed completion immediate. Deduplicate
replayed events. `Hear it` reads the displayed candidate on demand but playback
success never gates button confirmation.

### 9. Verification and evidence are gate outputs

Unit tests cover state transitions, provenance, token binding/invalidation,
idempotency, placement, fitting, mapping validation, and recovery. Contract
tests cover OpenAPI/client parity, error codes, manifests, provider schemas, and
Realtime tools. Integration tests cover upload through persisted export and all
version/authorization failures. Corpus tests cover the twelve authority
categories and negative files. Browser tests cover both typed paths, fake voice,
comparison, both destinations, revision, partial export, keyboard-only use,
microphone denial, disconnect, mobile viewer, and download.

The screenshot matrix uses 1440x1000, 1024x1366, and 390x844. A gate needs at
least 90/100 overall, no score category below 80%, no critical accessibility
defect, and no anti-reference violation. Evidence is tied to one commit SHA in
`artifacts/v2`; a build alone is not completion.

### 10. Freeze shared contracts before parallel implementation

The lead alone owns dependency manifests/lockfiles, routing, global tokens,
domain/state types, API/OpenAPI contracts, and integration merges. A frontend
integrator may own vendored Untitled primitives and isolated feature
screens/tests. A document integrator may own PDF adapters, fixtures, and corpus
tests. A voice integrator may own the Realtime adapter and its tests only after
the relevant domain/API contracts freeze. A read-only reviewer can inspect any
area. No more than three implementation agents run concurrently after Gate 0.

## Risks / Trade-offs

- [Fourteen-day scope] → Cut P1 and ornament first; never cut source grounding,
  exact review, typed fallback, deterministic PDF integrity, or evidence.
- [PDF variability] → Fail closed on ungrounded content, use appendix for safe
  grounded ambiguity, and grow support only through checksum-pinned fixtures.
- [EmbedPDF package/license drift] → Pin one package family version, inspect
  installed tarball licenses, and exclude cloud/server components before Gate 1.
- [Unicode/font mismatch] → Vendor licensed fonts, test required glyphs before
  review, and include Unicode corpus fixtures and extracted-text assertions.
- [Provider nondeterminism] → Strict schemas, closed-world validation, recorded
  responses, a measured model gate, and typed/provider-failure fallbacks.
- [Cloud Run concurrency] → GCS generation CAS, versioned mutations, immutable
  objects, idempotent operations, and persistence-across-revision tests.
- [Large frontend bundles] → Route-level splits and assertions that `/` omits
  PDF/Realtime while direct typed flow omits Realtime.
- [Legacy style leakage] → Route-scope V1 styles and delete the route and old
  component dependencies only after cutover evidence exists.
- [Synchronous request limits] → Enforce input bounds, explicit timeout/error
  behavior, and measure the corpus against Cloud Run's 300-second envelope.

## Migration Plan

1. Complete and commit Gate 0 authorities, audit synthesis, conflict decisions,
   this OpenSpec rebaseline, dependency plan, and clean baseline verification.
2. Add the V2 design-system/provider shell and authentic PDF spike while V1
   remains reachable at `/legacy`; roll back by routing `/app` to V1.
3. Complete every fixture-driven state and its evidence before enabling real
   persistence, PDF, Responses, or Realtime integrations.
4. Freeze `/api/v2` and domain contracts, then integrate FastAPI/GCS/document
   work and generated frontend types in bounded slices.
5. Add Responses and Realtime behind environment-controlled adapters only after
   deterministic typed flow passes; disable provider flags to roll back.
6. Promote one tested image digest to staging, prove durable assignments and
   complete gates, then remove legacy code/dependencies and deploy production.
7. Preserve immutable source/export evidence and the previous deployable image
   for rollback; schema changes remain additive during P0.

## Open Questions

None. Package-license confirmation, semantic-model selection, PDF thresholds,
and live-provider quality are specified gate measurements with deterministic
fallbacks, not unresolved implementation choices.
