# Claros V2 Baseline Audit

- **Status:** Gate 0 synthesis baseline
- **Recorded:** 2026-09-04
- **Baseline commit:** `5fb217715e4b3278f21a882b2652d928f2cca628`
- **V2 branch:** `codex/claros-v2-nerdy`

## Scope and authority

This document carries the completed repository audit forward. The V2 authority
documents were reviewed as a delta; the repository was not re-audited. Prior
findings remain valid unless the V2 delta below explicitly supersedes them.

Authority order:

1. `CLAROS_V2_SOL_ULTRA_EXECUTION_PRD.md`
2. `CLAROS_V2_PRODUCT_CONTRACT.md`
3. `CLAROS_V2_DESIGN.md`
4. Accepted V2 tests, fixtures, and evaluation thresholds
5. Current tracked implementation
6. Git history as an implementation reference
7. Old generated visual artifacts as anti-references only

The three repository-root authority copies are byte-identical to the supplied
files:

| Authority | SHA-256 |
|---|---|
| Execution PRD | `B8A3DF1D316D7FDC3A59D1503A17095AFBBF566F43102745436EDA1166E52FCA` |
| Product contract | `A511D27655D06BB7AF8887CA3D30A87626405C4B8FBA7ADFFC9595A0BDE959D8` |
| Design system | `9412CEAB312686BB4420C658ED3BB398BC781E2EB31FBF3ADA16E0353CFB4D61` |

## Current implementation baseline

### Repository and runtime

- The audited baseline was clean, on `main`, and synchronized with
  `origin/main` at `5fb2177`; V2 work proceeds on
  `codex/claros-v2-nerdy` from that commit.
- The current application is React 19, Vite, TypeScript, Tailwind, Radix,
  XState, React-PDF, React Dropzone, resizable panels, Storybook, Vitest,
  Playwright, and axe.
- The browser application is concentrated in `src/ui/Workspace.tsx`; domain
  contracts, placement logic, and the XState workflow live under `src/domain`.
- The current backend is a Node `/api/v1` service backed by an in-memory map.
  It is a V1 demonstration server, not a production persistence layer.
- Routes are `/`, `/app`, and a wildcard that returns the landing screen.
  Direct production navigation to `/app` returns 404 because the current
  server has no SPA fallback.

### Product behavior

- Upload accepts only the exact authored demo-PDF hash. It does not parse the
  supported document class and exposes only the first page.
- The current contract assumes one deterministic answer area directly below
  every accepted question on the same page. It rejects missing regions rather
  than using an attached answer page.
- The current experience is a resizable PDF/editor workspace, not the V2
  question-first hierarchy.
- Review, commit, and export exist, but replaying a plan token increments the
  assignment revision instead of returning the original result. The token is
  therefore neither truly single-use nor idempotent.
- Placement logic is duplicated between browser and server paths; unit tests
  primarily exercise the client copy rather than the server authority.
- The continuation behavior produces a one-page inline-style derivative and
  has no real appendix pagination.
- Export does not revalidate the immutable source generation or placement
  evidence and currently substitutes unsupported characters rather than
  preserving ordinary Unicode.
- There is no durable assignment restoration. The in-memory server loses
  assignment truth on process or instance replacement.
- Typed entry is available when voice is unavailable. Voice is browser
  speech-recognition scaffolding rather than the required Realtime/WebRTC
  implementation.

### Verification already established by the prior audit

These results describe the unmodified `5fb2177` baseline. Gate 0 reruns them
after the planning-only changes and records fresh output in `STATUS.md`.

| Check | Audited result |
|---|---|
| `npm run build` | Passed; application chunk approximately 578 KiB minified and PDF worker approximately 1.37 MiB |
| `npm test` | Passed; 7 Vitest tests |
| `npm run test:e2e` | Passed; 4 Playwright tests, including axe and desktop/mobile screenshots |
| `npm run build-storybook` | Passed |
| `openspec validate claros-reconstruction --strict` | Passed for the pre-V2 OpenSpec |

Current screenshot evidence is under `test-results/`, including landing and
workspace views at desktop and mobile sizes. This evidence is the V1 visual
baseline, not proof of V2 quality.

### OpenSpec baseline

- The active change is `openspec/changes/claros-reconstruction`.
- Its V1 task list records 17 of 19 tasks complete. The unfinished tasks are
  the evidence-backed parser/corpus and durable storage/live-provider work.
- The current four capabilities are `worksheet-contract`, `answer-integrity`,
  `student-workspace`, and `safe-export`.
- There are no archived/base specifications under `openspec/specs` to support
  a clean competing V2 delta. The active change must be updated in place, with
  the 17/19 V1 history retained as disposition history rather than V2 progress.
- Several current requirements encode V1-only behavior: mandatory same-page
  answer regions, all answers before export, no voice confirmation, the
  resizable PDF-primary workspace, and the Node/in-memory deployment shape.

## Historical recovery boundary

Commit `6963fbe` and historical branch `origin/codex/stage14-product-audit`
contain useful backend evidence. They are references, not a restoration point.

| Disposition | Historical material |
|---|---|
| Recover invariants and focused fixtures | Identifier validation; immutable source hashes; GCS conditional writes; finite/in-bounds geometry; source revalidation; scratch-fit-before-write; failed-upload cleanup; relevant parser/export test cases |
| Rewrite behind V2 contracts | FastAPI schemas and services; manifest and storage adapters; physical extraction; semantic mapping; geometry resolution; exporter; deployment workflows |
| Discard from V2 | OCR and scanned-PDF handling; Gemini integrations; teacher review; manual placement or coordinate editing; reconstructed-source PDFs; PyMuPDF runtime; migration-heavy compatibility code |

Useful historical filenames include `main.py`, `storage.py`, `manifest.py`,
`assignment_service.py`, `session_service.py`, `document_model.py`,
`document_pipeline.py`, `exporter.py`, and focused evaluation tests. Each must
be evaluated against a frozen V2 interface before any code is reused.

## V2 authority delta

The new authorities invalidate only these prior conclusions:

- A safely grounded question no longer needs an inline region. Deterministic
  code routes an insufficient or unsafe region to an attached answer page.
- Export begins after one confirmed answer and leaves unanswered questions
  blank.
- Untitled UI React is the sole visible V2 component foundation and EmbedPDF
  is the V2 source renderer. Radix and React-PDF are legacy-only during
  migration.
- FastAPI, private GCS, and immutable manifests/objects become production
  authorities; Node and in-memory state remain temporary V1 references.
- Both direct and guided paths support speech and complete typed operation.
  Realtime can create a candidate but cannot approve it or control geometry.
- Exact review and the phrase **Use this exact answer** are mandatory; a
  revision invalidates the previous confirmation.
- Exact approved Unicode text must survive persistence and PDF export without
  truncation, substitution, or silent paraphrase.
- The normal workspace is question-first. Source context supports the task and
  becomes a full-screen dialog on mobile rather than a permanent editor.

All other audit facts—including build health, current test scope, the
monolithic workspace, sample-hash gate, duplicated placement authority,
missing durable storage, direct-route 404, and historical recovery candidates—
remain in force.

## Gate 0 completion boundary

Gate 0 is planning-only. It is complete only when the authority files, all five
V2 synthesis documents, and the in-place OpenSpec rewrite are committed on the
V2 branch; authority hashes, strict OpenSpec validation, dependency audit,
baseline regressions, screenshot existence, and `git diff --check` must all be
recorded. Production dependencies and source code begin in Gate 1.
