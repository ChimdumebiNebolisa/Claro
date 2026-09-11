# Claros V2 gated execution

All active V2 tasks below begin unchecked. A gate may be marked complete only
after its command output and required artifacts are recorded for one commit SHA.
Later gates depend on every earlier gate; a later success cannot waive an
earlier failure.

## Ownership boundaries

| Owner | Exclusive write scope after contracts freeze | Must not change |
|---|---|---|
| Lead | Dependencies and lockfiles, routing, global tokens/providers, domain/XState types, API/OpenAPI schemas, integration merges, gate status | Nothing shared may be delegated without a recorded handoff |
| Frontend integrator | Vendored Untitled primitives, isolated V2 feature screens, stories, and component tests | Dependencies, global tokens, routes, domain/API contracts |
| Document integrator | PDF adapters, physical extraction, geometry/export internals, corpus fixtures and PDF tests | API schemas, browser state, global dependencies |
| Voice integrator | Realtime browser adapter, server credential implementation, policies, and isolated tests after schemas freeze | Confirmation semantics, candidate origins, routes, shared state types |
| Reviewer | Read-only inspection and evidence scoring | All tracked files |

No more than three implementation agents may run concurrently after Gate 0
unless the lead records a specific reason and disjoint scopes in `docs/v2/STATUS.md`.

## V1 disposition (historical record; not active V2 tasks)

The previous plan ended at **17 completed of 19 tasks**. These rows intentionally
do not use checkboxes and therefore do not count toward V2 progress.

| V1 task | Prior state | V2 disposition |
|---|---|---|
| 1.1 Vite/React/TypeScript shell | Complete | Retain framework baseline; supersede product flow |
| 1.2 OpenSpec integration/specialist lock | Complete | Retain repository integration |
| 1.3 Root and engineering guidance | Complete | Amend through V2 authorities and decisions |
| 2.1 Zod worksheet/domain contracts | Complete | Rewrite against FastAPI OpenAPI and V2 domain |
| 2.2 Deterministic placement classifier | Complete | Recover tests/invariants; replace sample geometry |
| 2.3 XState workspace graph | Complete | Rewrite for equal paths, comparison, review, and partial export |
| 2.4 Node demo/session/plan/export | Complete | Preserve under legacy route; replace with FastAPI/GCS |
| 2.5 Domain/state tests | Complete | Retain useful assertions and expand for V2 |
| 3.1 V1 tokens and responsive styles | Complete | Preserve Inter/focus ideas; replace visible foundation |
| 3.2 V1 landing page | Complete | Replace with authority-approved V2 marketing |
| 3.3 Upload/unsupported states | Complete | Reuse recovery concepts; replace sample-hash admission |
| 3.4 V1 workspace and export states | Complete | Preserve as legacy; rebuild V2 question-first states |
| 4.1 Production build | Complete | Baseline evidence only; rerun at every applicable gate |
| 4.2 Focused Vitest suites | Complete | Baseline evidence; expand for V2 contracts |
| 4.3 HTTP vertical-slice exercise | Complete | Baseline evidence; replace `/api/v1` coverage |
| 4.4a Storybook/a11y/Playwright harness | Complete | Retain and expand for V2 state matrix |
| 4.4 Browser screenshots and a11y automation | Complete | Baseline evidence; replace with V2 matrix and scoring |
| 4.5 Native-text parser and corpus | Incomplete | Superseded by Gate 3 document-understanding work |
| 4.6 Durable storage/TTL/live voice | Incomplete | Superseded by Gates 3 and 5 |

## 0. Gate 0 — Authority, audit, and decision freeze

- [x] 0.1 [Lead] Add the three V2 authority files at repository root byte-for-byte and verify their SHA-256 hashes equal the values recorded in `docs/v2/STATUS.md`.
- [x] 0.2 [Lead] Consolidate the six read-only audits into `BASELINE_AUDIT.md`, preserving prior repository/build/test/browser findings and adding only authority-driven deltas; verify every finding links to a path, command, screenshot, or commit.
- [x] 0.3 [Lead] Complete `CONFLICTS.md`, `DECISIONS.md`, and `RISKS.md` with authority resolutions, recovery/discard boundaries, dependency/license plan, branch, legacy route, API/PDF/voice decisions, and P0/P1 cuts; verify no material contradiction remains unowned.
- [x] 0.4 [Lead] Rebaseline this OpenSpec proposal, design, eight capability specs, and Gate 0–7 task graph; verify with `openspec validate claros-reconstruction --strict`.
- [x] 0.5 [Lead] Record exact first-phase ownership and commands in `docs/v2/STATUS.md`; verify production code has no Gate 0 diff and the active branch is `codex/claros-v2-nerdy` from audited commit `5fb2177`.
- [x] 0.6 [Lead] Re-run `npm ci`, `npm run ci`, `npm run build-storybook`, and `npm run test:e2e`; verify output and baseline screenshots are stored under the Gate 0 evidence record.
- [x] 0.7 [Lead] Run `npm audit --audit-level=high`, authority hash checks, dependency-diff review, `git diff --check`, and a read-only contract review; verify no unavailable audit, HIGH/CRITICAL runtime issue, or unresolved critical finding remains.
- [x] 0.8 [Lead] Commit the planning-only Gate 0 checkpoint and update `docs/v2/STATUS.md` with commit SHA, results, risks, and next action; verify the committed tree contains no production-code changes from Gate 0.

## 1. Gate 1 — V2 foundation and authentic document rendering

**Dependency:** Gate 0 is passed and recorded.

- [x] 1.1 [Lead] Pin the approved Node 22-compatible Untitled, EmbedPDF, TanStack Query, Motion, MSW, OpenAPI, testing, and lint dependencies while retaining legacy-only packages; verify `npm ci`, package license inspection, and `npm audit --audit-level=high` pass.
- [x] 1.2 [Frontend integrator] Install only the approved free Untitled v8 primitives and wrap Claros-specific notices/cards without recreating ordinary controls; verify component stories preserve React Aria labels, focus, and keyboard behavior.
- [x] 1.3 [Lead] Add V2 semantic tokens, providers, route shell, SPA fallback rules, and route-scoped `/legacy`; verify route tests cover `/`, every `/app` shape, `/legacy`, `/health`, and an unknown non-API path without legacy CSS leakage.
- [x] 1.4 [Document integrator] Implement an authentic EmbedPDF sample crop and read-only full viewer with forbidden capabilities disabled; verify the real fixture renders, range requests work, modal focus restores, and no HTML worksheet recreation exists.
- [x] 1.5 [Frontend integrator] Establish deterministic V2 Storybook/MSW fixtures for empty, loading, ready, error, and document-viewer states; verify Storybook builds and its accessibility checks pass.
- [x] 1.6 [Lead] Add route-level lazy boundaries for PDF and Realtime code; verify production bundle evidence shows `/` loads neither stack and a direct typed flow loads no Realtime bundle.
- [x] 1.7 [Lead] Run format, lint, typecheck, unit, Storybook, production build, route smoke, and keyboard upload/dialog tests plus a CSP/WASM/worker production smoke; verify the empty V2 shell screenshot has no fake PDF or second visible design system.
- [x] 1.8 [Reviewer] Perform a read-only Gate 1 contract, dependency, accessibility, and browser review; verify all critical findings are fixed and record the checkpoint SHA in `docs/v2/STATUS.md`.

## 2. Gate 2 — Fixture-complete student and marketing UI

**Dependency:** Gate 1 is passed; shared routes, tokens, API types, and XState event contracts are lead-owned and frozen before parallel screen work.

- [x] 2.1 [Lead] Implement the complete V2 XState graph for upload, checking, ready, question choice, direct/guided work, comparison, exact review, confirmation, answer-added, revision, worksheet review, export, and recoverable errors; verify transition tests make exact review unavoidable and allow partial export only after confirmation.
- [x] 2.2 [Frontend integrator] Build upload, checking, unsupported, ready, equal path-choice, direct answer, and guided conversation screens from Untitled primitives; verify stories cover every required state and the transcript/editor cannot diverge.
- [x] 2.3 [Frontend integrator] Build wording comparison, exact review, inline/appendix destination, answer-added, revision, all-answer review, export progress/failure/complete, and download states; verify exact authority copy, provenance labels, one dominant action, and no internal telemetry appear.
- [x] 2.4 [Lead] Implement the fake Realtime adapter and MSW mutations for both voice/typed paths, rephrase, review, idempotent confirmation, version conflict, revision, partial export, and failures; verify deterministic unit and browser fixtures require no live provider.
- [x] 2.5 [Frontend integrator] Complete desktop, tablet, mobile, full-screen worksheet-dialog, 200-percent zoom, and reduced-motion layouts; verify task-first DOM order, no horizontal overflow, 44px targets, focus restoration, explicit live regions, and stacked mobile comparison.
- [x] 2.6 [Frontend integrator] Replace marketing with the required navigation, product promise, two paths, authentic running-product preview, dark trust section, limitations, accessibility framing, and CTA; verify no fabricated metric, integration, certification, pricing, sign-in, fake worksheet, or PDF/Realtime request appears.
- [x] 2.7 [Lead] Run unit/component/Storybook browser tests, Playwright direct and guided flows, axe, keyboard-only completion, focus, reduced-motion, 200-percent zoom, and mobile-overflow checks; verify all tests pass against fixtures.
- [x] 2.8 [Lead] Capture the complete required state matrix at 1440x1000, 1024x1366, and 390x844 from the running app; verify an initial score of at least 90/100, every category at least 80 percent, zero critical accessibility defects, and zero anti-reference violations.
- [x] 2.9 [Reviewer] Independently replay and score Gate 2 read-only; verify disagreements are resolved through new browser evidence and record the checkpoint SHA and final score in `docs/v2/STATUS.md`.

## 3. Gate 3 — FastAPI, durable assignments, and deterministic PDF engine

**Dependency:** Gate 2 passes; the lead freezes domain and `/api/v2` schemas before document and client integration proceed in parallel.

- [x] 3.1 [Lead] Add the Python 3.11 FastAPI service, stable error envelope, version/ETag conventions, complete `/api/v2` endpoint set, `/health`, static serving, and generated TypeScript client; verify OpenAPI contract tests and the no-drift CI command pass.
- [x] 3.2 [Lead] Implement signed owner sessions, same-origin mutations, 24-hour logical expiry, local development storage, private GCS immutable objects, owner hashes, generation CAS manifests, authorized Range source, and rate limits; verify ownership, expiry, Range, concurrency, restart, and production-fail-closed tests.
- [x] 3.3 [Document integrator] Implement content-based preflight and canonical physical IR with stable IDs, exact joiners, page transforms, bounds validation, hashing, and deterministic serialization; verify byte-identical repeated IR and stable rejection codes across the corpus.
- [x] 3.4 [Document integrator] Implement server-owned geometry priority, canonical coordinate transforms, scratch fitting, 12pt-to-10pt readable floor, collision checks, appendix fallback, and transformed-page conservatism; verify placement unit/property tests cover finite bounds, overlap, long text, ambiguity, and unchanged recomputation hashes.
- [x] 3.5 [Document integrator] Implement immutable-source cloning, ReportLab overlays/appendix pagination with vendored Noto Sans, pypdf assembly, pikepdf validation, export manifests, idempotent versioned export, and authorized download; verify exact Unicode, source hash, page order, fit, openability, and failed-publish cleanup tests.
- [x] 3.6 [Document integrator] Add the checksum-pinned twelve-category gold corpus plus encrypted, malformed, oversized, limit, stale-source, unsupported-glyph, and changed-placement negatives; verify expected counts/text/order/outcomes/codes and repeatability for every fixture.
- [x] 3.7 [Lead] Connect the fixture-complete browser to the real `/api/v2` client for upload, status, source context, typed candidates, review, confirmation, revision, partial export, and download; verify an end-to-end typed flow survives service restart without MSW or in-memory truth.
- [x] 3.8 [Lead] Build and run the production container on the dispatchable Ubuntu GitHub runner with local test configuration, then exercise `/health`, `/`, `/app`, Range source, gold-workbook upload, confirm, export, parser reopen, and container restart; verify Cloud Run-compatible startup, bounded timeouts, privacy-safe uploaded logs, and exported-PDF workflow artifacts. Local Docker Desktop availability is optional.
- [x] 3.9 [Lead] Run frontend checks, `python -m ruff check backend scripts`, full pytest/coverage, corpus evaluation, OpenAPI drift, remote container smoke, dependency audits, parser/manual PDF checks, live GCS persistence, Cloud Run revision persistence, ownership isolation, and managed-proxy identity checks; verify all accepted and rejected cases meet Gate 3 requirements before integrating Gate 4 or Gate 5.
- [x] 3.10 [Reviewer] Perform read-only PDF, API, storage, authorization, and evidence review; verify critical findings are fixed and record the checkpoint SHA in `docs/v2/STATUS.md`.
- [ ] 3.11 [Document integrator] Promote the validated OpenPDF worker into the real `/api/v2` export path behind explicit engine selection, Java 21 and pinned font packaging, bounded process/resource limits, and qpdf plus PDFBox publication gates; verify inline and appendix output, exact Unicode/ligature text, immutable source, unconfirmed-draft exclusion, failure cleanup, PDF.js release compatibility, real-browser flow, and clean-worktree reproducibility without changing the deployed engine selection.

## 4. Gate 4 — Closed-world semantic mapping and optional rephrasing

**Dependency:** Gate 3 passes with frozen physical IR, candidate, and API contracts, including remote container smoke, live GCS persistence, Cloud Run revision persistence, ownership isolation, and managed-proxy identity evidence.

- [ ] 4.1 [Lead] Implement Responses adapters with strict mapping/rephrase schemas, `store: false`, no tools, bounded prompts, privacy-safe telemetry, recorded fixtures, and configurable models; verify provider contract tests reject forbidden fields and keep raw payloads out of logs.
- [ ] 4.2 [Lead] Implement the closed-world mapper prompt, diverse few-shot cases, exact block-ID validator, source-order/overlap rules, exact reconstruction, and safe refusal/timeout/malformed handling; verify unknown, duplicate, reordered, overlapping, ambiguous, and coordinate-bearing outputs all fail safely.
- [ ] 4.3 [Lead] Implement opt-in rephrasing with current-candidate preservation, strict factual-delta output, safe suggestion rejection, visible provenance, and no auto-selection; verify tests cover added facts, editing origin changes, selection, and separate confirmation.
- [ ] 4.4 [Lead] Run the required corpus benchmark in order Luna, Terra, Sol for three runs per candidate and select the first model meeting 100-percent required-gold correctness, zero invalid IDs, and the recorded p95 latency budget; verify the report captures fixture results, latency, cost observations, and chosen environment default.
- [ ] 4.5 [Lead] Exercise typed direct and guided fixture flows against real semantic mapping and rephrase while using recorded-provider CI responses; verify exact questions come only from source reconstruction and the model never controls geometry, approval, or PDF output.
- [ ] 4.6 [Lead] Run unit, schema, recorded-provider, corpus, integration, browser, privacy-log, and live-provider evaluation checks; verify failures preserve safe assignment state and no deterministic test depends on a live provider.
- [ ] 4.7 [Reviewer] Perform read-only prompt-injection, closed-world, provenance, corpus, and evidence review; verify critical findings are fixed and record the checkpoint SHA in `docs/v2/STATUS.md`.

## 5. Gate 5 — OpenAI Realtime direct and guided voice

**Dependency:** Gate 4 passes; confirmation, candidate, question-context, and credential schemas are frozen.

- [ ] 5.1 [Voice integrator] Implement owner/question/mode/version-authorized short-lived Realtime credentials and rate limits; verify stale, expired, cross-owner, and over-limit requests return stable errors and no standard OpenAI key reaches browser responses or bundles.
- [ ] 5.2 [Voice integrator] Add the pinned `@openai/agents` dependency and implement its WebRTC Realtime adapter, explicit text states, captions, audio tracks, start/stop/interrupt/mute controls, event deduplication, teardown, and one bounded reconnect; verify adapter tests cover every required event and release tracks on exit.
- [ ] 5.3 [Voice integrator] Implement direct-mode policy and narrow candidate actions; verify complete/fragment/clarification tests preserve student authorship and the transcript/editor share one candidate version.
- [ ] 5.4 [Voice integrator] Implement guided-mode one-question policy, bounded/collapsible turns, typed turns through the same adapter, readiness, and final-answer capture; verify transcript-only content never becomes a candidate or confirmation.
- [ ] 5.5 [Lead] Bind the canonical phrase `Use this exact answer` to the normal confirmation mutation only in fresh exact review, and implement `Hear it`; verify casual agreement and out-of-state phrases cannot confirm while playback failure leaves button/keyboard confirmation available.
- [ ] 5.6 [Voice integrator] Implement permission, connection, audio, provider, and reconnect recovery that preserves draft/turn state and offers retry/typing; verify denial and disconnect browser tests finish the question without reload, re-upload, or duplicate candidate.
- [ ] 5.7 [Lead] Run fake-adapter browser suites, accessibility/caption/mute checks, credential/security tests, bundle/key scans, and documented manual live direct/guided/interrupt/reconnect tests; verify all Gate 5 evidence passes.
- [ ] 5.8 [Reviewer] Perform read-only voice-authority, privacy, accessibility, failure, and evidence review; verify critical findings are fixed and record the checkpoint SHA in `docs/v2/STATUS.md`.

## 6. Gate 6 — Cutover, hardening, and deployment

**Dependency:** Gates 0–5 pass on the same integration line.

- [ ] 6.1 [Lead] Connect all real V2 adapters, exclude mocks from production, and verify no sample-hash-only, in-memory assignment, client geometry, or provider bypass remains in `/app` production bundles and runtime.
- [ ] 6.2 [Lead] Complete `/app` cutover, remove `/legacy`, `/api/v1`, and only now-unused Radix, React-PDF, dropzone, resizable-panel, Lucide, legacy server/style dependencies; verify dependency graph, route tests, build, and full regression suite contain one product generation and one visible component system.
- [ ] 6.3 [Lead] Complete security/privacy hardening and run npm/pip audits, secret scan, container/image scan, CSP/cookie/origin/rate-limit tests, dependency-license review, and log inspection; verify no unresolved HIGH/CRITICAL runtime issue, credential exposure, public GCS object, or sensitive content log remains.
- [ ] 6.4 [Lead] Run full unit, contract, integration, PDF corpus, recorded-provider, fake-Realtime, Storybook, Playwright, axe, keyboard, 200-percent zoom, reduced-motion, performance, and production build suites for one commit; verify every check and budget passes.
- [ ] 6.5 [Lead] Capture and independently review the final screenshot matrix and browser flow; verify at least 90/100 overall, every category at least 80 percent, zero critical accessibility defects, zero anti-reference violations, and authentic PDF rendering.
- [ ] 6.6 [Lead] Build one FastAPI/Vite image and configure Cloud Run, private GCS, Artifact Registry, Workload Identity Federation, least-privilege identities, Secret Manager, `/health`, 2 CPU, 2 GiB, concurrency 4, 300-second timeout, and min 1/max 1 while the limiter is process-local; verify infrastructure/deploy configuration contains no manual secret or public-object step and do not raise the maximum until a shared or edge limiter passes.
- [ ] 6.7 [Lead] Deploy the tested image digest to staging and exercise clean-session upload, source Range, both typed paths, rephrase, exact confirmation, revision, partial inline/appendix export, download, expiry, and a Cloud Run revision replacement; verify state and immutable artifacts survive and outputs open in Chrome and Acrobat.
- [ ] 6.8 [Reviewer] Perform independent read-only production contract, accessibility, security, visual, PDF, and deployment replay; verify every critical finding is fixed before production promotion and record the Gate 6 SHA/image digest in `docs/v2/STATUS.md`.

## 7. Gate 7 — Demonstration and release evidence

**Dependency:** Gate 6 passes and the production candidate is frozen except for verified release blockers.

- [ ] 7.1 [Lead] Select and checksum the strongest licensed/synthetic biology fixture and prepare a deterministic clean-browser demo path; verify it exercises grounded questions, inline and appendix placement, and contains no private data.
- [ ] 7.2 [Lead] Replay direct voice, guided reasoning, visible rephrase comparison, exact confirmation, answer-added, revision/reconfirmation, partial export, microphone denial, Realtime disconnect, and typed recovery against the deployed build; verify each outcome has browser and server evidence.
- [ ] 7.3 [Lead] Populate `artifacts/v2` with final screenshots, source/completed PDFs, test results, accessibility results, performance, visual scorecard, manual checklist, demo script, and final summary tied to commit and image digest; verify no required evidence path is missing.
- [ ] 7.4 [Lead] Update README setup, architecture, supported scope, privacy-safe configuration, verification commands, deployment, and honest limitations; verify a clean checkout can follow the documented local/container workflow without undisclosed manual steps.
- [ ] 7.5 [Lead] Record the two-to-three-minute demo and final technical summary; verify claims show both answer paths, both placement outcomes, exact approval, immutable source, recovery, real PDF download, and no unsupported adoption/compliance/integration statement.
- [ ] 7.6 [Reviewer] Perform an independent clean-browser release replay and submission-copy review; verify the deployed URL, final PDF, keyboard-only path, evidence links, supported-scope claims, and all P0 definition-of-done items pass.
- [ ] 7.7 [Lead] Commit the final release evidence, update `docs/v2/STATUS.md` and `artifacts/v2/final-summary.md` with exact commands/results/limitations/risks, and verify the submission uses the already-tested image digest with no foundational change after freeze.
