# Claros V2 Delivery Status

- **As of:** 2026-09-11
- **Branch:** `codex/claros-v2-nerdy`
- **Baseline:** `5fb217715e4b3278f21a882b2652d928f2cca628`
- **Current phase:** Gate 4 ready — Gate 3 is passed; OpenPDF renderer promotion is verified locally
- **Gate state:** Gates 0–3 passed; Windows Docker Desktop remains optional
- **Gate 0 content checkpoint:** `0c15404b87edbbe19b03de93d81ad95aa1e897fd`
- **Gate 1 content checkpoint:** `59cbc509650cc4a65b139a7db23012ead74efb3c`
- **Gate 2 content checkpoint:** `0723303ef718bb28594d519da31ec0a55226fa45`
- **Gate 3 accepted clean checkpoint:** `88cda664f55abf698a1d56567e814e024708ad0a`

## Current milestone

- **OpenPDF promotion:** The validated Java renderer is integrated behind
  explicit `CLAROS_PDF_ENGINE=openpdf` selection in the real `/api/v2` service.
  OpenPDF output is quarantined behind qpdf and PDFBox; PDF.js is a CI/release
  compatibility check only. The Cloud Run template remains explicitly set to
  `current`, and no deployment or infrastructure mutation is part of this work.
- **Promotion verification:** Focused real-endpoint and failure-path tests pass
  locally with Java 21.0.10, OpenPDF 3.0.5, PDFBox 3.0.8, qpdf 12.3.2, and the
  allowlisted Noto Sans Regular font. Clean-worktree, real-browser, sample PDF,
  PDF.js release compatibility, resource timing, and failure-injection evidence
  are recorded in `artifacts/v2/openpdf-migration/verification.md`. Task 3.11 is
  complete; Docker/production activation remains separately blocked and
  unauthorized.

- **Milestone:** Gate 3 passed at accepted clean checkpoint `88cda66`.
- **Changed:** Added the FastAPI `/api/v2` service, signed anonymous ownership,
  filesystem/GCS adapters, generation-CAS manifests, generated browser types,
  deterministic physical IR and placement, immutable-source inline/appendix
  export, gold corpus, real typed browser integration, and deployment assets.
- **Verified:** Node 22 CI and browser suites passed; 392 tracked Gate-3-only
  backend tests passed at 92-percent branch coverage; audits, strict OpenSpec,
  Terraform validation, authority hashes, Chrome/pikepdf/Acrobat reopening,
  Ubuntu production-container restart, Cloud Build, and live GCS/Cloud Run
  revision replacement all passed.
- **Remote evidence:** GitHub run `33941739290` retained privacy-safe logs and
  both synthetic PDFs. Cloud Build `8bcf24be-5be9-4e81-a8e5-fc2947d39754`
  produced digest `sha256:b4058b7bb22210a82690db7859354dad4fdf354441d57ee46a79deea6d7d5b66`;
  revision `claros-00075-xtv` serves it at 100 percent after live persistence,
  ownership-isolation, and proxy-identity checks.
- **Next action:** Begin Gate 4 only from the frozen physical-IR, candidate,
  placement, and API contracts. Keep the untracked semantic/Realtime draft
  trees excluded until their respective gate work is deliberately started.

## Gate 0 checklist

- [x] Use `codex/claros-v2-nerdy` from exact commit `5fb2177`.
- [x] Copy all three V2 authorities to the repository root byte-for-byte.
- [x] Verify all three SHA-256 values.
- [x] Read all three authorities in full and apply their authority order.
- [x] Preserve prior audit findings; record only the V2-invalidated delta.
- [x] Create `docs/v2/BASELINE_AUDIT.md`.
- [x] Create `docs/v2/CONFLICTS.md`.
- [x] Create `docs/v2/DECISIONS.md`, including dependencies and ownership.
- [x] Create `docs/v2/RISKS.md`.
- [x] Create `docs/v2/STATUS.md`.
- [x] Rewrite the active OpenSpec capabilities and task graph in place.
- [x] Preserve the V1 17/19 history as disposition, not V2 progress.
- [x] Run and record `openspec validate claros-reconstruction --strict`.
- [x] Run and record post-synthesis baseline regression checks.
- [x] Run and record `npm audit --audit-level=high`.
- [x] Verify current screenshot evidence still exists.
- [x] Inspect dependency and production-source diffs; both are unchanged.
- [x] Run and record `git diff --check`.
- [x] Complete an independent read-only authority/OpenSpec contract review with
      no blocking contradiction found.
- [x] Commit the Gate 0 planning-only checkpoint.

## Prior baseline evidence

The following passed on the unmodified baseline before the V2 authority delta:

| Evidence                                                  | Result                    |
| --------------------------------------------------------- | ------------------------- |
| `npm run build`                                           | Pass                      |
| `npm test`                                                | Pass — 7 tests            |
| `npm run test:e2e`                                        | Pass — 4 Playwright tests |
| `npm run build-storybook`                                 | Pass                      |
| Pre-V2 `openspec validate claros-reconstruction --strict` | Pass                      |

The existing browser evidence is in `test-results/`: landing desktop/mobile,
workspace desktop, and mobile worksheet/answer states. It is retained only as
the V1 baseline. Gate 2 produces the full V2 matrix under
`artifacts/v2/screenshots/`.

## Fresh Gate 0 verification — 2026-09-04

| Command/evidence                                      | Result                                                                   |
| ----------------------------------------------------- | ------------------------------------------------------------------------ |
| `npm ci`                                              | Exit 0; 357 packages installed; install audit reported 0 vulnerabilities |
| `npm run ci`                                          | Exit 0; production build passed and 7/7 Vitest tests passed              |
| `npm run build-storybook`                             | Exit 0; static Storybook build completed                                 |
| `npm run test:e2e`                                    | Exit 0; 4/4 Chromium Playwright tests passed                             |
| `npm audit --audit-level=high`                        | Exit 0; 0 vulnerabilities                                                |
| `openspec validate claros-reconstruction --strict`    | Exit 0; change valid                                                     |
| Authority SHA-256 checks                              | All three exact expected hashes matched                                  |
| `Get-ChildItem -Recurse .\test-results -Filter *.png` | Existing V1 browser screenshots present                                  |
| Production/dependency diff                            | Empty for `package.json`, lockfile, `src`, and `server`                  |
| Authored-file `git diff --check`                      | Exit 0; no whitespace errors                                             |
| Independent read-only contract review                 | No blocking authority, governance, or OpenSpec contradiction found       |

The verbatim authority imports contain ten intentional Markdown hard-break
lines with trailing double spaces. `git show --check 0c15404` reports those
lines. They are preserved because changing them would violate the required
byte-for-byte hashes; all authored Gate 0 files pass the whitespace check.

## Fresh Gate 1 verification — 2026-09-04

All commands in this table used Node `v22.23.2` where Node was involved.

| Command/evidence                                   | Result                                                                                                                                                        |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm ci`                                           | Exit 0; clean install of 763 packages; install audit reported 0 vulnerabilities                                                                               |
| `npm run ci`                                       | Exit 0; format, lint, typecheck, dependency/license contract, 27/27 Vitest tests, Storybook build, Storybook axe, production build, and bundle closure passed |
| `npm run test:e2e`                                 | Exit 0; 7/7 Chromium tests passed against fresh development and production servers                                                                            |
| `npm audit --audit-level=high`                     | Exit 0; 0 vulnerabilities                                                                                                                                     |
| `npm run check:dependencies`                       | Verified 17 exact versions/licenses, seven approved Untitled primitives, Node 22 engine, and retained legacy dependencies                                     |
| `npm run check:bundles`                            | Verified four marketing entry chunks exclude PDF/Realtime and all lazy boundaries exist                                                                       |
| Authentic document evidence                        | `renderPageRect` crop and full EmbedPDF viewer rendered the checked-in PDF through byte Range requests                                                        |
| Accessibility/keyboard evidence                    | Seven V2 Storybook states passed axe; upload and modal flows passed keyboard, focus restoration, 44px target, and mobile-overflow assertions                  |
| CSP/WASM/worker evidence                           | Built app loaded PDFium WASM and worker under production CSP; `/` made no PDF/Realtime request                                                                |
| `openspec validate claros-reconstruction --strict` | Exit 0; change valid                                                                                                                                          |
| Authority SHA-256 checks                           | All three exact expected hashes still match                                                                                                                   |
| `git diff --check`                                 | Exit 0; no whitespace errors                                                                                                                                  |
| Independent read-only Gate 1 review                | Approved with no critical/blocking finding; vendor-upgrade risk retained in `RISKS.md`                                                                        |

The production and Storybook builds report two accepted pinned-EmbedPDF
warnings: browser externalization of a package `crypto` import and large lazy
viewer chunks. Real crop/full-view execution passes in Chromium under the
production CSP, and the marketing static closure contains neither stack. Gate 6
must repeat this proof before cutover.

## Fresh Gate 2 verification — 2026-09-04

All Node commands in this table used Node `v22.23.2`. Browser evidence and the
visual scorecard are bound to content checkpoint
`0723303ef718bb28594d519da31ec0a55226fa45`.

| Command/evidence                                   | Result                                                                                                                                                                                             |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm run ci`                                       | Exit 0; format, lint, typecheck, dependency/license contract, 63/63 Vitest tests, Storybook build, all-story axe, production build, and bundle closure passed                                      |
| Storybook browser sweep                            | 36/36 V2 stories rendered; zero automated accessibility violations                                                                                                                                 |
| `playwright test`                                  | Exit 0; 22/22 serialized Chromium tests passed against fresh Vite/API servers in 3.1 minutes                                                                                                       |
| Direct and guided workflows                        | Exact review remained mandatory; casual voice agreement could not confirm; typed fallback, captions, interruption, rephrase selection, revision, and reconfirmation passed                         |
| Partial export and recovery                        | Export became available after one confirmed answer; unanswered questions remained blank; failure retry and authenticated fixture download passed                                                   |
| Authentic document evidence                        | Question-bound Q1/Q2/Q3 EmbedPDF crops, completed-copy preview, byte-Range source, decoded mobile full viewer, and source-preservation copy passed                                                 |
| Responsive/accessibility evidence                  | Task-first DOM order, 1440x1000/1024x1366/390x844 layouts, keyboard-only completion, focus restoration, 200-percent-equivalent reflow, reduced motion, no overflow, and principal-route axe passed |
| `node scripts/verify-gate2-screenshots.mjs`        | Verified 36 exact captures, dimensions, SHA-256 values, checkpoint SHA, and zero external requests                                                                                                 |
| Lead and independent visual score                  | 95/100; every authority-rubric category at least 90 percent; zero critical accessibility defects and zero anti-reference violations                                                                |
| `npm audit --audit-level=high`                     | Exit 0; 0 vulnerabilities                                                                                                                                                                          |
| `openspec validate claros-reconstruction --strict` | Exit 0; change valid                                                                                                                                                                               |
| Authority SHA-256 checks                           | All three exact expected hashes still match                                                                                                                                                        |
| `git diff --check`                                 | Exit 0; no authored whitespace errors                                                                                                                                                              |

The first expanded Playwright replay exposed five test-harness defects: lazy
cold-start timing, two ambiguous text locators, an assertion applied to the
guided path instead of only direct typing, and a DOM-order check made before the
workspace mounted. Each was corrected without weakening product assertions;
the focused five-test replay and the subsequent complete 22-test replay passed.
The final visual review is recorded in
`artifacts/v2/gate2-visual-scorecard.md`.

## Fresh Gate 3 verification — 2026-09-04

The complete record is in `artifacts/v2/gate3/verification.md` and is bound to
accepted clean checkpoint `88cda664f55abf698a1d56567e814e024708ad0a`.

| Command/evidence                   | Result                                                                                                                                                                      |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm run ci` under Node `v22.22.0` | Exit 0; format, lint, typecheck, dependency/license contract, OpenAPI drift, 73/73 Vitest tests, Storybook build and axe sweep, production build, and bundle closure passed |
| `npm run test:e2e`                 | Exit 0; 22/22 fixture Chromium flows passed                                                                                                                                 |
| `npm run test:e2e:gate3`           | Exit 0; the real FastAPI typed/partial-export flow survived a service restart                                                                                               |
| Gate-3-only pytest                 | 392 tracked tests passed with 92-percent branch coverage; 23 third-party deprecation warnings                                                                               |
| Focused reviewer replay            | 90 API/storage/PDF/security tests passed; all critical code findings were fixed                                                                                             |
| Ruff format/lint                   | All tracked Python sources formatted correctly and lint-clean                                                                                                               |
| Dependency audits                  | `npm audit --audit-level=high` reported 0 vulnerabilities; `pip-audit -r requirements-server.txt` found none                                                                |
| Terraform                          | Format, lockfile-readonly initialization, and validation passed with Terraform 1.15.2 and Google provider 7.46.0                                                            |
| Document corpus                    | Twelve checksum-pinned categories plus all required negative classes passed determinism, exact-text, placement, and failure-code checks                                     |
| Manual PDF reopening               | The same SHA-bound inline/appendix export opened correctly in Chrome and Adobe Acrobat 64-bit with source content intact and no appendix truncation                         |
| Authority/OpenSpec/whitespace      | Authority hashes matched; strict OpenSpec and diff checks passed                                                                                                            |
| Production container               | GitHub Ubuntu run `33941739290` passed for clean head `88cda66`; artifact `9962065063` retains both privacy-checked logs and parser-reopened inline/appendix PDFs           |
| Remote source build                | Cloud Build `8bcf24be-5be9-4e81-a8e5-fc2947d39754` built the clean committed archive and published immutable digest `sha256:b4058b7b…d5b66`                                 |
| Live GCS/Cloud Run replacement     | Revisions `claros-00074-kxl` → `claros-00075-xtv` passed live GCS persistence, ownership isolation, forged-proxy identity, inline/appendix export, and parser reopen        |
| Deployed privacy                   | 69 Cloud Logging entries scanned with zero worksheet, answer, cookie/token, or credential canary matches                                                                    |

The implementation reserves 30 seconds beneath the 300-second Cloud Run
request ceiling, bounds GCS RPCs and retries, persists owner-recoverable
analysis failures, and lets unsafe higher-priority placement candidates fall
through deterministically to lower-priority classes. These fixes were included
before the checkpoint and exercised through both remote acceptance paths.

## Gate 0 evidence commands

Run from the repository root in PowerShell and retain the complete output:

```powershell
git branch --show-current
git rev-parse HEAD
Get-FileHash -Algorithm SHA256 .\CLAROS_V2_SOL_ULTRA_EXECUTION_PRD.md
Get-FileHash -Algorithm SHA256 .\CLAROS_V2_PRODUCT_CONTRACT.md
Get-FileHash -Algorithm SHA256 .\CLAROS_V2_DESIGN.md
npm ci
npm run ci
npm run build-storybook
npm run test:e2e
npm audit --audit-level=high
openspec validate claros-reconstruction --strict
Get-ChildItem -Recurse .\test-results -Filter *.png
git diff -- package.json package-lock.json src server
git status --short -- package.json package-lock.json src server
git diff --check
git status --short
```

Expected authority hashes are listed in `BASELINE_AUDIT.md`. The dependency and
production-source diff must be empty for Gate 0. Any HIGH/CRITICAL runtime
finding or unavailable npm audit keeps Gate 1 blocked.

## Delivery gates

| Gate | Deliverable                                                                            | Blocking evidence                                                                                             | State                        |
| ---- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| 0    | Authorities, synthesis, in-place OpenSpec, dependency/ownership plan                   | Hashes, baseline regressions, npm audit, strict OpenSpec, clean production diff, planning commit              | Passed at `0c15404`          |
| 1    | Untitled foundation, V2 routes/providers, scoped legacy, authentic EmbedPDF spike, MSW | Build/tests, route and keyboard smoke, CSP/WASM/worker proof, no PDF request from `/`                         | Passed at `59cbc50`          |
| 2    | Fixture-complete V2 UI and fake Realtime                                               | Unit/component/Storybook/Playwright/axe, keyboard/focus/zoom/motion, full screenshot matrix, visual score ≥90 | Passed at `0723303` — 95/100 |
| 3    | FastAPI, GCS adapters, physical IR, placement/export, gold corpus                      | Python/API/PDF integration, deterministic IR, exact Unicode, immutable source, container/revision smoke       | Passed at `88cda66`          |
| 4    | Responses semantic mapping and rephrase                                                | Recorded/live corpus evaluation, zero invalid IDs, exact reconstruction, safe failure and provenance          | Not started                  |
| 5    | Realtime direct and guided paths                                                       | Fake browser suite and manual live voice/recovery/security evidence                                           | Not started                  |
| 6    | Cutover, hardening, deployment                                                         | Full accumulated CI/security/a11y/visual/performance/staging evidence                                         | Not started                  |
| 7    | Repeatable demo and release bundle                                                     | Clean-browser replay, final PDF, deployed smoke, honest submission copy, complete `artifacts/v2`              | Not started                  |

## Gate command contract

Gate 1 adds stable scripts for frontend format, lint, typecheck, unit,
Storybook/browser, build, E2E, accessibility, visual, and API-drift checks.
Gate 3 adds Ruff, pytest contract/PDF/integration coverage, pip-audit, corpus,
container, and `/health` smoke commands. Each later gate reruns every applicable
earlier command against one recorded commit SHA. Manual Chrome/Adobe Reader,
keyboard, live voice, visual, and deployment checks are retained as signed
checklist evidence rather than represented as automation.

## Fixed defaults

- P0 document limits: 10 MiB, 1–8 pages, at most 40 questions.
- Export answer floor: 10pt; fit begins at 12pt.
- Anonymous assignment TTL: 24 hours absolute.
- Review token TTL: 10 minutes, single-mutation with idempotent exact replay.
- P0 processing: bounded synchronous analysis/export with reload-safe status.
- Source delivery: same-origin, authorized, Range-capable proxy.
- Production: one stateless FastAPI/Vite Cloud Run service plus private GCS.
- Health endpoint: `/health`.
- Realtime default: `gpt-realtime-2.1`; semantic default is selected by the
  Gate 4 corpus benchmark.
- P0 restoration: owning browser session only; cross-device/shareable resume
  remains P1.

## Gate 0 exit statement

Gate 0 passed after every checklist item produced objective evidence and the
planning-only checkpoint changed no dependency, production-source, generated
UI, or runtime file. `DECISIONS.md` freezes the Gate 1 interfaces and
`RISKS.md` supplies its stop conditions.

## Gate 1 exit statement

Gate 1 passed at content checkpoint
`59cbc509650cc4a65b139a7db23012ead74efb3c`. The Node 22 clean-install evidence,
full automated checks, real PDF browser evidence, dependency/license audit, and
independent review have no blocking finding. The only retained concerns are
explicit upgrade/cutover risks in `RISKS.md`; they do not weaken any Gate 1
acceptance invariant.

## Gate 2 exit statement

Gate 2 passed at content checkpoint
`0723303ef718bb28594d519da31ec0a55226fa45`. The fixture-complete workflow,
authentic source and completed-copy views, responsive matrix, full automated
checks, and independent 95/100 review have no blocking finding. This checkpoint
does not claim durable assignment truth, dynamic PDF placement/export, a live
semantic model, or live WebRTC; those boundaries remain blocked behind Gates
3–5 exactly as required.

## Gate 3 exit statement

Gate 3 passed at accepted clean checkpoint
`88cda664f55abf698a1d56567e814e024708ad0a`. Local contract, storage,
document, browser, security, corpus, audit, and manual PDF evidence passed. The
head-associated Ubuntu workflow tested the immutable pull-request merge
revision containing that checkpoint, built and restarted the production
container, and retained privacy-checked logs plus reopened PDFs. The
owner-authorized Cloud Run deployment then proved GCS persistence across
revision replacement, cross-owner denial, managed-proxy identity behavior,
exact digest use, and live browser export/reopen. Windows Docker Desktop is
optional and was not used as acceptance evidence. Tasks 3.8 and 3.9 are
complete; later gates remain unimplemented and must preserve the frozen Gate 3
contracts.
