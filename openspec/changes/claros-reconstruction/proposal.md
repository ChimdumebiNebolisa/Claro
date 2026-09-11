## Why

Claros must replace its sample-only V1 reconstruction with a production-capable,
accessibility-first worksheet workflow before the Nerdy AI Hackathon deadline.
The V2 authorities require exact source grounding, equal direct and guided answer
paths, mandatory exact review, deterministic PDF placement, durable anonymous
assignments, and evidence from the running product rather than mockups.

## What Changes

- **BREAKING** Rebaseline the active reconstruction from the V1 sample-only
  slice to the V2 product contract and Gate 0–7 delivery program.
- **BREAKING** Replace the Node in-memory `/api/v1` production path with a
  stateless FastAPI `/api/v2` service backed by private Google Cloud Storage;
  retain V1 temporarily at `/legacy` only for migration evidence.
- **BREAKING** Replace Radix-based V2 controls with Untitled UI React and
  replace `react-pdf` with authentic, read-only EmbedPDF rendering.
- Accept native-text sequential short-answer PDFs within explicit limits,
  derive deterministic physical evidence, and use model-selected block IDs to
  construct exact ordered questions without model-owned geometry.
- Give every unanswered question two equally weighted paths—direct answering
  and guided reasoning—with a complete typed path at every voice state.
- Preserve candidate provenance, make rephrasing opt-in and visibly
  comparative, and require exact-text review before any answer is confirmed.
- Resolve placement deterministically to inline, attached answer page, or safe
  rejection; lack of inline room alone is never a rejection.
- Export a derivative from immutable source bytes and current confirmed
  answers, including partial assignments, exact Unicode, and validated
  appendix pages where needed.
- Promote the validated OpenPDF renderer behind explicit engine selection, a
  bounded Java process boundary, and mandatory qpdf plus PDFBox publication
  gates; retain PDF.js as CI/release compatibility evidence only.
- Add signed anonymous access, optimistic concurrency, idempotent confirmation
  and export, Realtime WebRTC credentials, security/privacy boundaries, a gold
  PDF corpus, and browser/PDF/accessibility evidence gates.

## Capabilities

### New Capabilities

- `worksheet-contract`: Define accepted document limits, grounded-question
  readiness, stable rejection behavior, and safe student projections.
- `answer-integrity`: Define provenance, optional rephrasing, mandatory exact
  review, answer-bound confirmation, revision, and exact-text preservation.
- `student-workspace`: Define the question-first, responsive, accessible
  upload-to-export experience and its truthful visible states.
- `safe-export`: Define immutable-source derivative generation from confirmed
  answers, deterministic placement revalidation, and authorized download.
- `document-understanding`: Define deterministic physical IR, closed-world
  semantic block mapping, exact reconstruction, and corpus validation.
- `deterministic-placement`: Define coordinate authority, placement priority,
  readable fitting, appendix fallback, and safe rejection.
- `assignment-lifecycle`: Define `/api/v2`, signed anonymous ownership, durable
  GCS state, versioning, TTL, concurrency, and privacy/security behavior.
- `voice-guidance`: Define direct and guided Realtime behavior, captions,
  narrow mutation boundaries, exact-state voice confirmation, and recovery.

### Modified Capabilities

None. No base specifications have been archived; all eight capability files
remain new deltas within this active change.

## Impact

- Rebuilds the V2 route hierarchy while preserving the current app under
  `/legacy` until the Gate 6 cutover.
- Introduces FastAPI, GCS, the Python analysis/geometry stack, the maintained
  Java 21/OpenPDF worker, qpdf and PDFBox validators, OpenAI Responses, OpenAI
  Realtime, Untitled UI React, EmbedPDF, TanStack Query, Motion, MSW, and
  generated OpenAPI client contracts.
- Replaces sample-hash admission, client-coordinated placement, ASCII export,
  in-memory assignment truth, and all-answers-required export behavior.
- Adds gold-corpus, contract, integration, browser, accessibility, visual,
  security, deployment, and demo evidence under the gated execution plan.
