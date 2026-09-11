# Claros V2 Sol Ultra Execution PRD

**Status:** Authoritative implementation specification  
**Version:** 1.0  
**Date:** 2026-09-04  
**Target:** Nerdy AI Hackathon submission  
**Repository:** `ChimdumebiNebolisa/Claros`  
**Execution model:** GPT-5.6 Sol in Ultra mode, acting as lead engineer and orchestrator

---

## 0. Read this first

This is not a request for another design concept, isolated mockup, or speculative architecture document.

The task is to turn the current Claros repository into a runnable, visually premium, accessibility-first product that completes one narrow workflow end to end:

```text
understand the exact worksheet question
-> let the student answer directly or think it through
-> preserve the student's final choice
-> place only the approved answer into a usable completed PDF
```

The implementation must be built and evaluated in the browser. Do not use image generation as a substitute for interface implementation. Do not recreate a worksheet with HTML. Do not handcraft ordinary controls that already exist in the selected component system.

### 0.1 Required source files

Before editing code, locate and read all of the following:

1. `CLAROS_V2_SOL_ULTRA_EXECUTION_PRD.md`, this document.
2. `CLAROS_V2_PRODUCT_CONTRACT.md`.
3. `CLAROS_V2_DESIGN.md`.
4. Root `AGENTS.md` and any nested `AGENTS.md` files.
5. The active OpenSpec change and repository-specific OpenSpec skills.
6. Current `README.md`, `package.json`, tests, API adapters, state machine, PDF fixture, and server implementation.
7. Relevant git history for the prior FastAPI, Google Cloud Storage, Gemini Live, parser, and PDF exporter implementation.

Do not assume the current branch still contains the historical production backend. Inspect it.

### 0.2 Authority order

When sources conflict, use this order:

1. This execution PRD.
2. `CLAROS_V2_PRODUCT_CONTRACT.md` for product behavior.
3. `CLAROS_V2_DESIGN.md` for visual and interaction behavior.
4. Accepted tests, fixtures, and explicit evaluation thresholds added under this PRD.
5. Current tracked implementation.
6. Git history, only as an implementation reference.
7. Old generated HTML, screenshots, and design-board mockups, only as anti-references.

This PRD explicitly supersedes any earlier implementation guidance that says the V2 student interface must continue using Radix primitives or `react-pdf`. The new V2 visual foundation is Untitled UI React, and the new PDF viewing foundation is EmbedPDF. Existing Radix and `react-pdf` code may remain temporarily on the legacy route during migration, but they must not define the new V2 interface.

### 0.3 Resolve conflicts explicitly

Create `docs/v2/CONFLICTS.md` before implementation. Record every material contradiction found across the repository, the selected resolution, and the authority used. Do not silently blend incompatible generations of Claros.

---

# Part I: Sol Ultra operating contract

## 1. Why Ultra is being used

Ultra mode is appropriate because this work spans several separable domains:

- repository and git-history analysis;
- product-state and accessibility design;
- component-system integration;
- PDF extraction and export;
- API and persistence design;
- OpenAI semantic mapping;
- OpenAI Realtime voice integration;
- deterministic evaluation and visual QA.

The work benefits from parallel investigation, but parallel implementation is dangerous when agents share files, state contracts, CSS tokens, API schemas, or migration boundaries.

## 2. Ultra strengths to exploit

Use Ultra for:

1. **Parallel read-only investigation.** Assign independent audits to subagents before editing.
2. **Long-horizon execution.** Maintain a persistent plan and advance through explicit gates.
3. **Cross-repository reasoning.** Compare current main, git history, source contracts, and official library documentation.
4. **Design plus implementation.** Inspect the app in a browser, capture screenshots, identify visual defects, and iterate.
5. **Tool-driven repair loops.** Run builds, tests, browser checks, PDF checks, and accessibility scans after each milestone.
6. **Broad codebase consistency.** Update domain contracts, API types, tests, documentation, and UI together after interfaces are frozen.

## 3. Ultra failure modes to prevent

The following are operational risks, not optional stylistic concerns.

| Risk | Required mitigation |
|---|---|
| Subagents implement conflicting versions | All Phase 0 subagents are read-only. Later write scopes must be disjoint and approved in the execution plan. |
| Model overbuilds because the context is large | Enforce P0, P1, and deferred scope. A feature outside P0 requires a written justification in `docs/v2/DECISIONS.md`. |
| Stale repository generations get blended | Use the authority order and `docs/v2/CONFLICTS.md`. Historical code is never restored wholesale. |
| Attractive mockups replace working software | Every visual claim must be proven by a browser-rendered screenshot from the running app. |
| “Done” is declared after code generation | Completion requires command output, passing tests, exported PDFs, and the full evidence bundle specified later. |
| Visual quality remains subjective | Use the 100-point visual scorecard and iterate until the threshold is met. |
| Agents duplicate dependency work | One lead owns dependency selection and lockfile changes. Subagents may recommend packages but may not install them during audit. |
| A subagent changes shared contracts without coordination | Only the lead may modify shared schemas, tokens, routing, state-machine types, or API contracts. |
| Long execution loses its place | Maintain `docs/v2/STATUS.md`, update it after every gate, and end each progress update with the next concrete action. |
| Destructive rewrite erases useful behavior | Preserve the current route until the V2 replacement passes cutover gates. No hard reset, force push, history rewrite, or blanket reversion. |

## 4. Mandatory execution pattern

Use this loop throughout the project:

```text
plan
-> inspect
-> implement one bounded change
-> run the relevant verification
-> inspect the actual result
-> repair failures
-> update status and decisions
-> continue only when the gate passes
```

Do not make five architectural changes and defer verification until the end.

## 5. Phase 0 subagent plan

Before any production edit, create the following read-only subagents. They may inspect files, git history, official documentation, tests, and the running baseline. They may not edit tracked files, install packages, or change the lockfile.

Operational limits:

- create exactly these six audit agents, not an unbounded hierarchy;
- audit agents may not spawn additional agents;
- after Phase 0, use at most three concurrent subagents unless the lead records why more are necessary;
- implementation agents must have disjoint write scopes;
- terminate or archive an agent when its bounded deliverable is complete.

### Agent A: Repository and migration audit

Deliver:

- current architecture map;
- current build, test, and run commands;
- current route map;
- current state-machine and domain-contract map;
- obsolete and reusable modules;
- relevant historical commits and files worth selectively recovering;
- migration risks.

### Agent B: Product and interaction audit

Deliver:

- state-by-state comparison between current behavior and the V2 contract;
- missing user states;
- contradictory copy;
- accessibility failures;
- recommendation for the V2 route structure;
- a list of product assumptions that must not be inferred.

### Agent C: Frontend and design-system audit

Deliver:

- current CSS/component inventory;
- Untitled UI React integration plan;
- exact base components needed, based on available free components;
- EmbedPDF integration options;
- responsive layout recommendation;
- anti-patterns found in the current or generated mockups;
- visual baseline screenshots.

### Agent D: PDF engine audit

Deliver:

- current parser and exporter behavior;
- current fixture limitations;
- useful historical parser/export code;
- proposed physical IR;
- license and dependency review;
- gold-corpus plan;
- exact failure modes and deterministic checks.

### Agent E: OpenAI integration audit

Deliver:

- current Gemini and browser voice boundaries, including history;
- proposed Responses API semantic-mapping contract;
- proposed Realtime WebRTC and ephemeral-credential flow;
- tool and guardrail design;
- failure and reconnect behavior;
- test doubles required before live integration.

### Agent F: Verification audit

Deliver:

- current test coverage and gaps;
- proposed unit, contract, integration, browser, accessibility, visual, and PDF test suites;
- screenshot matrix;
- evidence bundle structure;
- CI migration plan.

## 6. Phase 0 synthesis gate

The lead must combine the six reports into:

- `docs/v2/BASELINE_AUDIT.md`;
- `docs/v2/CONFLICTS.md`;
- `docs/v2/DECISIONS.md`;
- `docs/v2/RISKS.md`;
- `docs/v2/STATUS.md`;
- an OpenSpec proposal and task list aligned with this PRD.

Before writing production code, the lead must state:

1. The exact V2 branch or worktree being used.
2. Which legacy route remains available during migration.
3. Which historical modules will be recovered, rewritten, or discarded.
4. Which dependencies will be added, removed later, or retained temporarily.
5. The file ownership boundaries for the first implementation phase.
6. The commands that define the first gate.

Do not ask the user to re-decide matters already settled in this PRD. Ask only when a truly blocking ambiguity remains after repository inspection.

## 7. Progress reporting

Use short milestone updates, not narration of every command. Each update must contain:

```text
Milestone:
Changed:
Verified:
Remaining risk:
Next action:
```

A milestone is not complete when verification is still pending.

---

# Part II: Product definition

## 8. Product sentence

Claros helps students who find typing difficult answer a worksheet directly or talk through a difficult question, review the exact final wording, and place only the approved answer into a completed PDF.

## 9. Product category

**Accessibility-first, voice-first worksheet completion workspace.**

Claros is not primarily:

- a chatbot;
- a PDF editor;
- an automatic homework-answer generator;
- an all-purpose K-12 platform;
- an educator dashboard;
- a generic dictation tool.

## 10. Primary audience

Students who can express ideas more easily than they can enter sustained text with a keyboard. This includes students affected by dysgraphia, motor limitations, temporary injury, fatigue, pain, or other input barriers. A diagnosis is not required.

The demo uses secondary-school short-answer worksheets. The public product must not claim comprehensive K-12 coverage or target direct under-13 consumer use.

## 11. Core promise

> The answer is yours. Getting it onto the page can be easier.

Supporting copy:

> Say what you know or talk through what you do not. Claros turns your input into a reviewable answer and places only the version you approve onto the worksheet.

Trust line:

> Nothing is written to the completed PDF until you approve the exact text.

## 12. Core loop

```text
worksheet context
-> direct answer or guided reasoning
-> reviewable final wording
-> explicit student approval
-> reliable PDF completion
```

## 13. Two equal entry paths

Every unanswered question begins with two equally weighted options.

### Path A: Say my answer

Use when the student already knows the answer.

```text
speak or type
-> normalized draft
-> optional visible rephrasing
-> exact review
-> explicit approval
-> place approved text
```

### Path B: Help me think it through

Use when the student wants guidance.

```text
state uncertainty
-> one focused guiding question
-> develop the idea
-> student states final answer
-> exact review
-> explicit approval
-> place approved text
```

Neither path is labeled recommended. Difficulty typing must not be equated with difficulty understanding.

## 14. Answer provenance

Every answer candidate has one internal origin:

```text
student_verbatim
student_normalized
claros_rephrase
student_after_guidance
student_edited
```

The student-facing UI exposes only the meaningful distinction:

- **Your words**
- **Suggested wording**

Claros may normalize punctuation, capitalization, and obvious speech disfluencies. It may not silently introduce a new factual claim. A clearer rephrasing must be requested, displayed beside the original version, selected, and then approved.

## 15. Non-negotiable behavioral rules

1. The active question and its source evidence are explicit.
2. Typed input remains available at every voice state.
3. Tutoring transcript is not a final answer.
4. No model infers approval from casual agreement.
5. Exact review is mandatory before placement.
6. A revision invalidates the old confirmation.
7. The uploaded source PDF is never overwritten.
8. The semantic model may return source block IDs, never authoritative coordinates.
9. Deterministic code owns geometry and export.
10. Unsupported layouts fail clearly instead of being guessed.
11. Unsafe or oversized answers use an attached answer page.
12. The final PDF preserves the exact approved answer text.

---

# Part III: Scope

## 16. P0, required for the hackathon submission

P0 must work end to end in the deployed application:

1. Upload a native-text PDF worksheet.
2. Validate limits and supported document class.
3. Extract physical blocks and source coordinates.
4. Map source blocks into ordered short-answer questions.
5. Render the actual source PDF.
6. Navigate question by question.
7. Choose either direct answer or guided reasoning.
8. Use typed input through the complete flow.
9. Use live voice through both answer paths.
10. Display live captions and explicit voice states.
11. Create and edit an answer candidate.
12. Request an optional visible rephrasing.
13. Review the exact answer and destination.
14. Confirm with button, keyboard, or the exact voice command in the dedicated review state.
15. Place safe answers inline on the derivative PDF.
16. Route unsafe or oversized answers to attached answer pages.
17. Revise a confirmed answer and require reconfirmation.
18. Export one completed PDF while preserving unanswered questions as blank.
19. Handle microphone failure with typed continuation.
20. Handle Realtime failure without losing the draft.
21. Deploy on Cloud Run with source and derivative PDFs in Google Cloud Storage.
22. Provide a polished landing page and a polished student workspace.
23. Pass the P0 evidence and acceptance gates in this PRD.

## 17. P1, only after all P0 gates pass

- resume an anonymous assignment through a signed session;
- read the exact answer aloud before voice confirmation;
- background page-preview generation;
- a compact all-answer review mode;
- basic keyboard shortcuts disclosed in help;
- download the untouched original PDF;
- performance instrumentation with privacy-safe event names;
- a second supported non-science worksheet in the public demo selector.

## 18. Deferred scope

Do not implement the following during P0:

- OCR or scanned-document support;
- multiple choice;
- freehand drawing;
- arbitrary math layout;
- tables requiring cell editing;
- teacher dashboards;
- classroom rostering;
- grading;
- LMS integrations;
- Google Classroom submission;
- accounts and billing;
- collaboration;
- analytics dashboards;
- mobile native apps;
- FERPA or COPPA certification claims;
- universal PDF compatibility;
- model-generated placement coordinates;
- drag-to-place or resize-to-fit controls;
- a general-purpose chat interface;
- gamification, streaks, points, mascots, or confetti.

---

# Part IV: End-to-end user simulation

## 18.1 Hackathon time box and priority rule

The submission deadline is September 18, 2026. Treat the project as a fourteen-day product sprint, not an open-ended platform rewrite.

Suggested schedule from September 4:

| Date window | Target |
|---|---|
| Sep 4 | Gate 0 audit, conflicts, architecture, branch, dependency plan |
| Sep 5-6 | Gates 1-2, design-system foundation and complete fixture-driven UI |
| Sep 7-10 | Gate 3, FastAPI, GCS, deterministic PDF engine, gold corpus |
| Sep 11 | Gate 4, semantic mapping and rephrasing |
| Sep 12-13 | Gate 5, Realtime direct and guided paths |
| Sep 14-15 | Gate 6, integration, accessibility, visual QA, deployment |
| Sep 16 | Record demo and produce submission assets |
| Sep 17 | Independent replay, bug buffer, final submission review |
| Sep 18 | Submission only, no foundational rewrite |

When schedule pressure appears, cut P1 and visual ornament before cutting the core loop, PDF correctness, exact review, typed fallback, or evidence. The build should make a Nerdy engineering reviewer infer that the team can ship a polished AI product, not that the team can accumulate features.

---

## 19. Canonical demo user

Use a fictional high-school student completing a biology worksheet. The student understands some questions and needs guidance on others. The demonstration must show competence, not helplessness.

## 20. Journey 1: Direct answer

1. Student opens the app and selects the official biology sample.
2. Claros verifies the worksheet and reports the number of supported questions.
3. Question 1 appears with the exact prompt and source context.
4. Student chooses **Say my answer**.
5. Student speaks a complete answer.
6. Claros displays the transcript under **Your words**.
7. The student edits one word or keeps the normalized version.
8. Claros shows exact review and where the answer will appear.
9. The student selects **Use this exact answer**.
10. The answer appears in the validated region on the worksheet preview.
11. Claros advances only after showing the saved state.

## 21. Journey 2: Guided reasoning

1. Student opens Question 2 and chooses **Help me think it through**.
2. Claros asks one focused question grounded in the worksheet prompt.
3. The student responds by voice.
4. Claros asks a second question only if needed.
5. Claros asks the student to state the final answer.
6. The student states it.
7. The transcript does not become final automatically.
8. The final candidate appears under **Your words** or **Your answer after guidance**.
9. The student may request **Make it clearer**.
10. The UI displays original and suggested wording side by side.
11. The student chooses one version.
12. Exact review appears.
13. The student confirms.
14. The exact selected text is persisted and placed.

## 22. Journey 3: Attached answer page

1. A confirmed answer exceeds the readable capacity of its original answer region.
2. Claros does not reduce the text below the minimum readable size.
3. Exact review says: **This answer will appear on an attached answer page.**
4. The student confirms.
5. The worksheet preview shows an unobtrusive reference marker, only if the export design requires it.
6. The attached page contains the exact source question, source page number, stable question identifier, and exact approved answer.
7. The final PDF keeps all original pages and appends the answer page.

## 23. Journey 4: Voice failure

1. Microphone permission is denied or the Realtime connection fails.
2. The current draft and conversation state remain intact.
3. The UI presents a clear error and an immediate **Continue by typing** action.
4. The student completes the question without reloading or restarting.

## 24. Journey 5: Unsupported document

1. Student uploads a scan or ambiguous worksheet.
2. Claros rejects it before creating a fake assignment.
3. The message states what is unsupported.
4. The screen offers the official sample and allows a different file.
5. No fabricated questions or answer regions appear.

---

# Part V: Final architecture

## 25. Architecture decision

```text
Claros
|
|-- Cloud Run, keep
|-- Google Cloud Storage, keep
|
|-- React application, rebuild the V2 flow
|   |-- React 19 + Vite + TypeScript
|   |-- Untitled UI React as the sole visible component foundation
|   |-- Tailwind tokens supplied by Untitled UI and Claros semantic tokens
|   |-- XState for visible workflow
|   |-- TanStack Query for server state
|   |-- Motion for bounded domain transitions
|   |-- Storybook + MSW for deterministic states
|   |-- EmbedPDF for actual PDF rendering
|   `-- OpenAI Agents SDK for Realtime voice
|
|-- FastAPI service, restore or rebuild selectively
|   |-- assignment and answer APIs
|   |-- signed anonymous session access
|   |-- GCS manifest persistence
|   |-- PDF preflight, parsing, placement, and export
|   |-- OpenAI semantic mapping
|   `-- ephemeral Realtime credential endpoint
|
|-- Document engine, rebuild behind explicit interfaces
|   |-- pikepdf preflight and normalization
|   |-- pdfplumber physical extraction
|   |-- OpenAI Structured Outputs semantic mapping
|   |-- deterministic geometry resolver
|   |-- ReportLab overlay and answer-page rendering
|   `-- pypdf derivative assembly
|
|-- OpenAI Realtime
|   |-- browser WebRTC
|   |-- short-lived credential from FastAPI
|   `-- direct answering and contextual tutoring
|
`-- OpenAI Responses
    |-- block-ID grouping and semantic classification
    |-- strict structured output
    `-- no authoritative geometry
```

## 26. Backend choice

Use Python 3.11+ and FastAPI for P0. The PDF stack is Python-native, and the repository history contains useful FastAPI, GCS, parser, and exporter work. Recover ideas and well-tested modules selectively, but do not revert to the historical branch wholesale.

The current sample-only Node server may remain temporarily to preserve the baseline route. It is not the P0 production backend.

## 27. Deployment shape

Use one Cloud Run service for P0:

- FastAPI serves `/api/v2/*`.
- The Vite production build is served as static assets by FastAPI or the container's static-serving layer.
- GCS stores source PDFs, derived PDFs, optional previews, and assignment manifests.
- Cloud Run instances remain stateless.
- No assignment truth may live only in an in-memory map.

Do not split into multiple services unless a measured blocker requires it.

## 28. GCS object layout

```text
assignments/{assignment_id}/source/original.pdf
assignments/{assignment_id}/manifest/assignment.json
assignments/{assignment_id}/previews/page-{page_number}.png
assignments/{assignment_id}/exports/{export_id}/completed.pdf
assignments/{assignment_id}/exports/{export_id}/manifest.json
```

Use immutable object names for source and exports. Use GCS generation preconditions when updating the assignment manifest to prevent silent lost updates.

---

# Part VI: Frontend system

## 29. Component-system decision

Use **Untitled UI React** as the sole visible component foundation for the V2 route.

### Required rules

1. Install only the necessary free components through the official Untitled UI CLI after confirming their current names.
2. Scaffold the Untitled UI Tailwind theme and global styles once.
3. Wrap vendored components behind local Claros APIs where product semantics differ.
4. Preserve React Aria behavior and accessible labeling.
5. Use `@untitledui/icons` for ordinary interface icons.
6. Do not install or use Opensource UI.
7. Do not add shadcn/ui, MUI, Mantine, Chakra, Radix Themes, React Aria components outside the Untitled UI layer, or another visible design system.
8. Existing Radix code may stay only on the legacy route during migration.
9. Do not handcraft ordinary buttons, inputs, textareas, radio groups, dialogs, sheets, tooltips, progress indicators, alerts, or file uploaders.
10. A component missing from the free kit may be composed from existing Untitled UI primitives. Do not add a second kit.

### Initial component inventory

Confirm exact CLI identifiers before installation. The V2 app requires capabilities equivalent to:

- buttons and utility buttons;
- file upload/drop zone;
- text area and text input;
- radio group or selectable cards;
- progress indicator;
- badges;
- alerts;
- modal or full-screen dialog;
- slideout or mobile sheet;
- tooltip;
- dropdown menu;
- skeleton/loading state;
- toast, used sparingly;
- navigation header;
- empty state.

Do not install tables, command menus, calendars, dashboards, or marketing sections that are not used.

## 30. PDF viewer decision

Use **EmbedPDF**.

### Full worksheet viewer

Use `@embedpdf/react-pdf-viewer` for the full worksheet modal or route. Disable unsupported categories such as annotation, print, and export when Claros provides its own controlled export path.

### Inline source context

The normal question screen should show a real PDF page or crop, not a fabricated HTML worksheet. Use EmbedPDF's lower-level integration or a controlled page viewport if required for question-region overlays. Do not use the experimental browser AI layout-analysis plugin. Document understanding belongs on the backend.

### Viewer behavior

- Fit the relevant page or region without tiny text.
- Offer **View full worksheet**.
- Preserve native page proportions.
- Show subtle question-region orientation, not a neon full-box treatment.
- Hide irrelevant editing tools.
- Support loading, error, and retry states.
- Keep the viewer subordinate to the question workflow on narrow screens.

## 31. Custom components allowed

Custom UI code is allowed only where Claros has domain-specific behavior not provided by the design system:

- `WorksheetViewport`
- `QuestionRegionOverlay`
- `CommittedAnswerOverlay`
- `AnswerPagePreview`
- `VoiceStateMeter`
- `AnswerPlacementTransition`
- adapters that wrap EmbedPDF or the OpenAI Realtime session

These components may compose Untitled UI primitives. They must not recreate base controls.

## 32. Visual direction

The student workspace must feel:

- calm;
- precise;
- accessible;
- mature;
- student-controlled;
- intentionally designed;
- visibly connected to the real worksheet.

It must not resemble:

- an enterprise dashboard;
- a design-board presentation;
- a PDF debugger;
- a generic chatbot;
- a children's game;
- a hand-built Tailwind component showcase.

## 33. Application layout

### Desktop, 1180px and wider

```text
+---------------------------------------------------------------------+
| 64px top bar: Claros | worksheet title | progress | Review / Export |
+-------------------------------------------+-------------------------+
|                                           |                         |
| Primary task workspace                    | Source context          |
| minmax(0, 1fr), max content width 760px   | fixed 400-440px         |
|                                           | actual PDF page/crop    |
| question, path, voice, answer, review     | View full worksheet     |
|                                           |                         |
+-------------------------------------------+-------------------------+
```

Rules:

- Task workspace is primary and first in DOM order.
- Source context is supporting, not a permanent editor.
- No required resize handle.
- No 50/50 split.
- No empty inspector containing two cards at the top.
- Keep the active task vertically centered only when content is short. Long content begins near the top and scrolls naturally.
- The top bar does not contain fake status telemetry.

### Tablet, 768px to 1179px

- Task workspace first.
- Compact source-context card below the active answer controls.
- Full worksheet opens in a modal or route.
- No horizontal overflow.

### Mobile, below 768px

- Single column.
- Sticky compact progress header.
- Question and active task first.
- Source context behind **View worksheet**.
- Full-screen worksheet sheet/dialog.
- Primary action reachable without precise dragging.
- No side-by-side wording comparison. Use stacked selectable cards.

## 34. Typography and control sizing

- Application font: Inter or Untitled UI's compatible sans-serif token.
- Application body: 16px target.
- Supporting text: 13px minimum.
- Question text: 24-32px on desktop, 22-28px on mobile.
- Primary control height: at least 44px.
- Text area: comfortable for a multi-sentence answer.
- Avoid 10px interface text.
- Avoid monospace except code or internal debug screens.
- Avoid all-caps ribbons and dense eyebrow labels.

## 35. Color and shape

Map Claros semantic tokens into the Untitled UI theme:

```css
--claros-ink: #111827;
--claros-muted: #5d6677;
--claros-quiet: #8b94a5;
--claros-line: #dfe5ef;
--claros-paper: #ffffff;
--claros-soft: #f7f9fc;
--claros-blue: #075ee8;
--claros-blue-dark: #064bbb;
--claros-blue-soft: #eef5ff;
--claros-green: #16835d;
--claros-green-soft: #ecf9f3;
--claros-amber: #ad6411;
--claros-amber-soft: #fff8e8;
--claros-error: #b42318;
```

Use:

- blue for primary action, focus, selected path, and active question;
- green only for completed or safely placed states;
- amber only for attention and attached-answer-page routing;
- red only for errors;
- pale blue atmosphere on marketing surfaces, not behind dense task text;
- solid, high-contrast application surfaces;
- 10-12px control radii;
- 14-18px workflow-card radii;
- subtle borders before shadows;
- no ordinary control glow.

## 36. Motion

Use Motion only for:

1. voice-state transitions;
2. answer candidate moving toward its worksheet destination;
3. question-to-question progression;
4. mobile sheet transitions supplied by the component system.

All meaning must remain clear with `prefers-reduced-motion`. The reduced-motion path updates state immediately and announces the result through an accessible status region.

## 37. Anti-reference checklist

The V2 app must not contain:

- a black design-board rail;
- numbered presentation headings such as “01 Main Desktop Workspace”;
- fake browser chrome inside the app;
- an HTML recreation of a PDF;
- a giant neon-blue active-question rectangle;
- labels such as “Student direction choice”;
- claims such as “Microphone calibrated” unless actually measured and relevant;
- claims about audio being exported to teachers;
- fake school metadata added for visual texture;
- raw coordinates, font metrics, parser confidence, or vector terminology;
- empty panels filled with tiny operational labels;
- nested cards used only to create visual complexity;
- gradients or glow as a substitute for hierarchy.

---

# Part VII: Screen and state specification

## 38. Route structure

Use the following route model unless the baseline audit identifies a concrete technical blocker:

```text
/                  marketing page
/app               V2 upload and workspace
/app/:assignmentId active assignment
/app/:assignmentId/review
/app/:assignmentId/export/:exportId
```

During migration, the old app may temporarily remain under `/legacy` or a feature-flagged route. Do not maintain two permanent product generations.

## 39. Marketing page

### Purpose

Explain the accessibility problem and prove the full transformation in under one viewport plus one scroll.

### Required structure

1. Navigation: Claros, How it works, Accessibility, Try Claros.
2. Hero headline and supporting copy from this PRD.
3. One real browser screenshot or live product preview from the implemented app.
4. Two paths section.
5. From speech or typing to exact review to PDF placement.
6. Dark trust section with four guarantees:
   - Choose your route.
   - See every wording change.
   - Approve the exact text.
   - Keep the source pages.
7. Accessibility framing.
8. Supported-PDF limitations stated plainly.
9. Final CTA.

### Forbidden

No fake usage metrics, customer logos, pricing, sign-in, LMS integrations, compliance badges, educator portals, or company-incorporation claims.

## 40. Upload state

### Required content

- headline: **Bring in a worksheet.**
- short explanation of supported native-text short-answer PDFs;
- Untitled UI file upload component;
- **Try the biology sample** secondary action;
- concise limitations link;
- visible keyboard-accessible file button.

### Validation

Validate file type and byte limit immediately. Server validation remains authoritative.

## 41. Document checking state

Show truthful, event-driven status. Do not animate invented progress percentages.

Possible steps:

```text
Reading pages
Finding questions
Checking answer areas
Preparing the worksheet
```

Only display a step as complete after the backend reports it complete. If the backend does not stream stages, use an indeterminate state and a single truthful message.

## 42. Worksheet-ready state

Show:

- worksheet title;
- page count;
- supported question count;
- inline-placement count, if already known;
- answer-page fallback count, if already known;
- unsupported warnings;
- **Start Question 1** primary action;
- **View worksheet** secondary action.

Do not expose model confidence or geometry data.

## 43. Question-choice state

Primary hierarchy:

1. `Question N of M` and progress.
2. Exact source question text.
3. Optional concise instruction or source-context note.
4. Two equal path cards.
5. Typed input fallback.
6. Source context.

Path cards:

### Say my answer

> Speak or type what you already know.

Action: **Start answering**

### Help me think it through

> Work through the question with Claros, one step at a time.

Action: **Start a guided conversation**

Do not preselect a path.

## 44. Direct-answer state

Required UI:

- exact question pinned;
- explicit state label: Ready, Listening, Captured, or Microphone unavailable;
- large primary microphone action;
- live caption/transcript area labeled **Your words**;
- editable text area using the same candidate source;
- **Type instead** available before and during voice;
- **Make it clearer** secondary action after a non-empty candidate;
- **Review answer** primary action.

The transcript and editable answer must not become divergent sources. There is one current candidate.

## 45. Guided-reasoning state

Required UI:

- exact question pinned;
- compact conversation history;
- one active Claros prompt at a time;
- student and Claros turns with restrained visual distinction;
- live captions;
- start, stop, interrupt, mute, and type controls;
- **I am ready to answer** action;
- no endless chatbot composer detached from the task.

Conversation behavior:

- Claros starts from the active question and source context.
- Claros asks one focused question at a time.
- Claros avoids long explanations unless requested.
- Claros does not produce the final answer without the student.
- Claros explicitly asks the student to state a final answer.
- Prior turns collapse when they obstruct the active task, but remain accessible.

## 46. Wording-comparison state

When **Make it clearer** is selected:

```text
Your words
[student-derived version]

Suggested wording
[model rephrasing]
```

Rules:

- both versions are visible;
- neither is falsely labeled as verbatim if it is not;
- selected version has a visible border, background, icon, and screen-reader state;
- selection updates the final candidate immediately;
- suggestion cannot add unsupported facts;
- **Keep my wording** and **Use suggestion** are explicit;
- editing either selected version changes origin to `student_edited`.

## 47. Exact-review state

This is the highest-risk and highest-importance state.

Required order:

1. Heading: **Review your exact answer**.
2. Instruction: **Read every word before it reaches the worksheet.**
3. Provenance: **Your words** or **Suggested wording**.
4. Exact final text in a high-contrast surface.
5. **Hear it** action.
6. Destination status:
   - **Your answer fits on the original worksheet.**
   - **This answer will appear on an attached answer page.**
7. **Change answer** secondary action.
8. **Use this exact answer** primary action.

Voice approval is accepted only while this state is active and only for the configured exact command. Casual “yes,” “okay,” and similar phrases are ignored.

Forbidden student-facing words:

- commit;
- inject;
- stamp;
- author lock;
- target space;
- placement token;
- semantic validation;
- immutable vector layer.

## 48. Confirming and answer-added states

On approval:

1. Disable duplicate submission.
2. Send the candidate version and confirmation token.
3. Show a truthful loading state.
4. Persist the confirmed answer.
5. Update the source-context overlay.
6. Announce: **Answer added to the worksheet.** or **Answer added to the attached answer page.**
7. Offer **Edit answer** and **Continue to Question N**.

Motion may connect the candidate card to the destination. The state must remain understandable without motion.

## 49. Worksheet review state

Show all questions in source order with:

- answered or unanswered state;
- a concise answer preview;
- origin label only when useful;
- inline or attached-page destination;
- edit action;
- jump-to-question action.

Do not show tutoring transcripts by default.

Primary action: **Download completed PDF**.

Export is allowed after at least one answer is confirmed. Unanswered questions remain blank.

## 50. Export state

Show:

- exporting progress or indeterminate state;
- failure with retry that preserves confirmed answers;
- completion with file name and size;
- **Download completed PDF**;
- **Review answers**;
- optional **Download original PDF** after P0.

The browser must download a real derivative PDF returned by the backend.

---

# Part VIII: Frontend architecture and ownership

## 51. State ownership

### XState owns

- upload workflow state;
- document-check state;
- current question and path selection;
- direct-answer substate;
- guided-reasoning substate;
- candidate review and comparison;
- confirmation state;
- answer-added transition;
- worksheet review and export flow;
- recoverable visible errors.

### TanStack Query owns

- assignment fetches;
- upload mutation;
- candidate and rephrase mutations;
- confirmation mutation;
- answer revision mutation;
- export mutation and status;
- cache invalidation;
- cancellation and retry policy.

### Realtime adapter owns

- connection lifecycle;
- microphone and audio tracks;
- transcript events;
- model turns;
- interruptions;
- tool-call events;
- reconnect attempts.

### Local component state owns only

- visual disclosure state;
- non-authoritative field focus;
- temporary menu or dialog visibility;
- animation state that does not affect product truth.

Do not store assignment truth in three separate layers.

## 52. Proposed frontend structure

Adapt to repository conventions after audit, but preserve these module boundaries:

```text
src/
  app/
    router.tsx
    providers.tsx
  features/
    assignment-upload/
    document-check/
    question-workspace/
    direct-answer/
    guided-reasoning/
    exact-review/
    worksheet-review/
    export/
  components/
    ui/                    vendored Untitled UI and local wrappers
    document/              EmbedPDF and overlay integrations
    voice/                 controlled Realtime UI
  domain/
    contracts.ts
    assignment-machine.ts
    candidate.ts
    placement.ts
  services/
    api/
    realtime/
  styles/
    globals.css
    claros-tokens.css
  test/
    fixtures/
    msw/
```

Do not force a complete directory rewrite if the current repository has a cleaner compatible structure. Document deviations.

## 53. API typing

FastAPI OpenAPI is authoritative for transport schemas. Generate or validate the TypeScript API client after the backend contract stabilizes. Do not maintain manually divergent request types in multiple files.

Zod may validate critical browser boundaries, but avoid duplicating every generated schema by hand.

---

# Part IX: Backend and API contract

## 54. Backend module boundaries

```text
backend/
  main.py
  api/
    assignments.py
    answers.py
    exports.py
    realtime.py
  domain/
    models.py
    errors.py
    confirmation.py
  document/
    preflight.py
    physical_ir.py
    semantic_mapping.py
    geometry.py
    renderer.py
    exporter.py
  storage/
    gcs.py
    manifests.py
  openai/
    client.py
    schemas.py
    tutor_policy.py
  tests/
```

Use existing historical modules only when their behavior and tests align with this contract.

## 55. Core API conventions

- Prefix new endpoints with `/api/v2`.
- Return machine-readable error codes and student-safe messages.
- Use stable IDs.
- Include assignment version or ETag on state-changing requests.
- Make confirmation single-use and answer-bound.
- Make export idempotent for a given assignment version.
- Do not return secrets, raw model prompts, or internal coordinates to the student UI unless coordinates are strictly required for rendering a verified overlay.
- Coordinates sent for overlays come from deterministic backend evidence, not model output.

## 56. Endpoint set

### `POST /api/v2/assignments`

Multipart upload or official sample creation.

Response, accepted:

```json
{
  "assignment_id": "asg_...",
  "status": "analyzing",
  "version": 1,
  "source": {
    "filename": "biology-worksheet.pdf",
    "page_count": 2
  }
}
```

Response, rejected:

```json
{
  "error": {
    "code": "requires_ocr",
    "message": "This PDF appears to be scanned. Claros V2 supports PDFs with selectable text.",
    "recoverable": true
  }
}
```

### `GET /api/v2/assignments/{assignment_id}`

Returns assignment status, questions, answers, version, and student-safe warnings.

### `GET /api/v2/assignments/{assignment_id}/source`

Returns an authorized source stream or short-lived signed URL for EmbedPDF.

### `GET /api/v2/assignments/{assignment_id}/pages/{page_number}/context`

Returns verified question-region data and optional preview asset.

### `POST /api/v2/assignments/{assignment_id}/questions/{question_id}/candidates`

Creates or replaces a candidate from typed or voice-derived student input.

Request:

```json
{
  "text": "Plants need sunlight to make food through photosynthesis.",
  "origin": "student_normalized",
  "assignment_version": 4
}
```

### `POST /api/v2/assignments/{assignment_id}/questions/{question_id}/rephrase`

Creates an optional suggested wording while preserving the original candidate.

Response includes both versions and a factual-delta safety result.

### `POST /api/v2/assignments/{assignment_id}/questions/{question_id}/review`

Returns exact candidate snapshot, placement outcome, readable rendering metadata, and a short-lived review token.

### `POST /api/v2/assignments/{assignment_id}/questions/{question_id}/confirm`

Request:

```json
{
  "review_token": "rvw_...",
  "candidate_id": "cand_...",
  "candidate_version": 3,
  "assignment_version": 4
}
```

The server verifies exact text, question binding, candidate version, assignment ownership, placement plan, token expiry, and single use.

### `PATCH /api/v2/assignments/{assignment_id}/questions/{question_id}/answer`

Begins revision of a confirmed answer. The old answer remains visible until the new candidate is confirmed, but export uses the latest confirmed version only.

### `POST /api/v2/assignments/{assignment_id}/exports`

Creates or returns an idempotent export for the current assignment version.

### `GET /api/v2/assignments/{assignment_id}/exports/{export_id}`

Returns status and authorized download information.

### `POST /api/v2/realtime/client-secret`

Creates a short-lived Realtime client credential after validating assignment access and active-question context.

Do not put the standard OpenAI API key in the browser.

## 57. Domain types

Minimum conceptual types:

```text
Assignment
SourceDocument
DocumentIR
PageIR
PhysicalBlock
Question
QuestionEvidence
AnswerRegion
AnswerCandidate
CandidateOrigin
ReviewSnapshot
PlacementDecision
ConfirmedAnswer
ConversationTurn
ExportManifest
```

## 58. Assignment invariants

- Questions remain in source order.
- Every question references exact source evidence.
- Every confirmed answer references one question and one candidate version.
- Review tokens are bound to exact text and placement.
- A candidate edit invalidates its prior review token.
- A confirmation updates assignment version.
- Export records the assignment version used.
- Source object generation never changes after assignment creation.

---

# Part X: Document engine

## 59. Supported V2 contract

P0 supports:

- native-text PDF;
- up to 10 MiB unless the audit justifies a different existing limit;
- up to 8 pages;
- up to 40 questions;
- sequential short-answer prompts;
- identifiable source question text;
- one plausible local answer region or attached-page fallback;
- no required OCR;
- no claim of arbitrary compatibility.

A question may be understood even when inline placement is unavailable. In that case, use an attached answer page. Reject only when the question or necessary context cannot be grounded safely.

## 60. PDF library stack

Use:

- `pikepdf` for opening, normalization, basic repair, metadata-safe handling, and final validation;
- `pdfplumber` for characters, words, lines, rectangles, and source coordinates;
- `reportlab` for Unicode-capable overlays and attached answer pages;
- `pypdf` for cloning and merging pages and assembling the derivative file.

Do not introduce PyMuPDF into the new P0 stack without a documented license decision. Historical PyMuPDF code may be used as a behavioral reference, not copied blindly.

## 61. Preflight

Preflight must determine:

- valid PDF signature and readable structure;
- byte limit;
- page limit;
- encryption or password protection;
- selectable text presence;
- rotation and crop boxes;
- malformed pages;
- unsupported scan-only behavior;
- font and Unicode constraints relevant to export.

Return stable rejection codes.

## 62. Physical IR

The physical parser is deterministic. Example:

```json
{
  "document_id": "doc_...",
  "pages": [
    {
      "page_index": 0,
      "width": 612,
      "height": 792,
      "rotation": 0,
      "blocks": [
        {
          "id": "p1_b14",
          "kind": "text",
          "text": "2. Why do plants need sunlight?",
          "bbox": [72, 181, 502, 207],
          "reading_order": 14
        },
        {
          "id": "p1_l15",
          "kind": "line",
          "bbox": [72, 230, 540, 231],
          "reading_order": 15
        }
      ]
    }
  ]
}
```

Physical truth includes coordinates. It is generated by code, not the model.

## 63. Semantic mapping

The OpenAI model receives a compact representation containing:

- stable block IDs;
- exact block text;
- page number;
- reading order;
- block kind;
- nearby relation hints derived deterministically;
- optional page image for semantic context when needed.

It returns strict structured output containing only:

- ordered question IDs;
- prompt block IDs;
- instruction/context block IDs;
- question type;
- whether the question depends on a diagram or external context;
- semantic warnings;
- no coordinates.

Example output:

```json
{
  "questions": [
    {
      "question_key": "q2",
      "prompt_block_ids": ["p1_b14"],
      "context_block_ids": [],
      "question_type": "short_answer",
      "depends_on_visual_context": false,
      "warnings": []
    }
  ]
}
```

The server validates every ID, order, overlap, and exact-text reconstruction. A schema-valid response is not automatically semantically valid.

## 64. Geometry resolver

Deterministic code decides placement using:

1. PDF form fields, when safely usable.
2. Rectangular writable boxes.
3. Groups of answer lines beneath the question.
4. Verified whitespace bounded by question and next content.
5. Attached answer page when no readable inline region exists.

The resolver produces:

```text
inline
appendix
reject
```

It must never produce “probably around here.”

## 65. Text fitting

Implement deterministic fitting with these rules:

- preserve exact approved text;
- wrap at word boundaries;
- support ordinary Unicode punctuation and accented characters;
- use an embedded font with broad coverage;
- do not reduce below the configured readable floor;
- do not overlap source content;
- do not cross validated region bounds;
- if text cannot fit, route to attached answer page;
- never truncate silently;
- never paraphrase to fit.

Set the initial readable floor through corpus testing, not arbitrary aesthetics. Start at 10pt for exported worksheet answers and document any deviation.

## 66. Attached answer page

Each appended entry contains:

- worksheet title;
- question number or stable display identifier;
- exact original question text;
- original source page number;
- exact approved answer;
- clear visual separation from other entries.

Do not rewrite the question. Do not omit necessary source-page reference.

## 67. Export

Export pipeline:

```text
load immutable source generation
-> load current confirmed answers
-> revalidate every placement against source evidence
-> render inline overlays
-> render attached answer pages
-> merge into a new PDF
-> validate page count, text presence, bounds, and openability
-> store immutable export object
-> return authorized download
```

The source object remains byte-identical in storage.

## 68. Corpus

Required gold corpus:

1. Polished high-school biology worksheet.
2. Middle-school science worksheet.
3. Non-science short-answer worksheet.
4. Blank-line answer regions.
5. Rectangular answer boxes.
6. Multi-page question order.
7. Long-answer appendix routing.
8. Unicode punctuation and names.
9. Rotated or non-default crop-box page.
10. No-safe-inline-region worksheet.
11. Controlled scanned-PDF rejection.
12. Ambiguous question-boundary rejection.

Generate synthetic variants where licensing or privacy makes real worksheets unsuitable.

---

# Part XI: OpenAI semantic and voice behavior

## 69. Responses API use

Use the Responses API with strict Structured Outputs for semantic block mapping and optional rephrasing. Keep model choice configurable through environment variables and measure quality on the gold corpus before locking a default.

Do not let the model:

- produce or modify physical coordinates;
- silently paraphrase source questions;
- decide confirmation;
- write directly to the PDF;
- invent missing worksheet content;
- bypass server validation.

## 70. Semantic mapping prompt contract

The semantic mapper prompt must state:

- the task is closed-world block selection;
- every returned ID must come from the input;
- source order must be preserved;
- ambiguity must be reported, not repaired creatively;
- question wording will be reconstructed exactly from selected blocks;
- coordinates are unavailable to and irrelevant to the semantic decision;
- output must match the supplied schema.

Include diverse few-shot cases:

- one-line question plus answer line;
- multi-line question;
- shared instruction followed by questions;
- question referencing a diagram;
- ambiguous headers;
- unsupported multiple-choice layout;
- no-question page.

## 71. Rephrasing contract

A rephrase request receives:

- exact source question;
- student's current candidate;
- limited relevant context;
- instruction to preserve meaning and factual claims;
- instruction to avoid adding an answer not already present;
- strict output containing suggestion and a short list of detected factual changes.

The backend rejects or flags a suggestion when a factual-delta check finds a new unsupported claim.

## 72. Realtime architecture

Use `@openai/agents/realtime` in the browser with WebRTC.

Flow:

1. Browser requests a short-lived credential from FastAPI.
2. FastAPI validates assignment access and active question.
3. Browser creates a `RealtimeAgent` and `RealtimeSession`.
4. Session connects with the short-lived credential.
5. Browser sends live audio.
6. Realtime events update captions and conversation state.
7. Server-side product mutations occur only through narrow authenticated tools or standard APIs.

## 73. Realtime tools

Permitted conceptual tools:

```text
get_active_question_context()
set_student_candidate(exact_text, source_turn_ids)
request_clearer_wording(candidate_id)
enter_exact_review(candidate_id)
report_voice_issue(code)
```

Do not expose:

```text
write_to_pdf(x, y, text)
approve_for_student()
export_without_confirmation()
rewrite_question()
select_arbitrary_question()
```

The final confirm operation remains an explicit application action. A voice command may trigger it only in the exact-review state and must pass the same server checks as a button.

## 74. Direct-answer agent policy

In direct mode:

- listen and transcribe;
- minimize conversational interruption;
- do not tutor unless asked;
- do not turn a fragment into a materially more complete answer without permission;
- ask a concise clarification only when needed to capture what the student intended;
- transfer the student's candidate into the deterministic review flow.

## 75. Guided-reasoning agent policy

In guided mode:

- ground every turn in the active question and provided context;
- ask one focused question at a time;
- prefer eliciting the student's knowledge over lecturing;
- do not give the final answer immediately;
- do not continue tutoring after the student indicates readiness;
- ask the student to state one final answer;
- transfer that answer into review without treating the conversation as approval.

## 76. Voice states

Expose explicit text states:

```text
Ready
Listening
Thinking
Speaking
Interrupted
Connection lost
Microphone unavailable
```

A waveform is supplementary. It is never the only status.

## 77. Voice recovery

- preserve the current candidate on disconnect;
- preserve visible conversation turns needed for the task;
- allow one bounded automatic reconnect attempt;
- show **Retry voice** and **Continue by typing**;
- never require re-uploading the worksheet;
- do not discard confirmed answers;
- do not create duplicate candidates from replayed events.

---

# Part XII: Accessibility, security, and privacy

## 78. Accessibility acceptance

The product is accessibility-first, so automated checks are necessary but insufficient.

Required:

- complete keyboard flow;
- logical focus order;
- visible focus indicators;
- minimum 44x44px primary targets;
- no drag-only or resize-only interaction;
- no color-only status;
- live captions for student and Claros speech;
- mute spoken output without losing text;
- typed fallback at every point;
- reduced-motion behavior;
- screen-reader announcements for analyzing, confirmation, placement, and export;
- question task before source context in mobile DOM order;
- headings and landmarks that reflect state hierarchy;
- no forced answering time limit;
- errors associated with their actionable controls.

Run axe, but also complete a manual keyboard pass and document it.

## 79. Privacy constraints

- Do not log PDF text, question text, answer text, audio content, transcripts, API keys, review tokens, or session secrets in operational logs.
- Use bounded status and error labels for telemetry.
- Do not claim that data is never retained or never used for training unless the implemented policy and provider settings support the claim.
- Delete or expire anonymous demo assignments according to a documented TTL.
- Do not expose GCS objects publicly.
- Use short-lived signed access or authenticated proxy routes.
- Keep the standard OpenAI API key and GCP credentials server-side.

## 80. Security constraints

- Validate upload type by content, not extension alone.
- Enforce byte, page, question, and extracted-text limits.
- Treat PDFs and model output as untrusted.
- Escape or render text through safe APIs.
- Bind review tokens to assignment, question, candidate ID, candidate version, exact text hash, placement hash, and expiry.
- Use constant-time comparison where secrets or signatures require it.
- Use SameSite, HttpOnly, Secure cookies where cookies are used.
- Protect state mutations from cross-assignment access.
- Avoid browser local storage for bearer secrets.
- Rate-limit expensive analysis and Realtime-secret creation.
- Scan dependencies and document any unresolved high-severity issue.

---

# Part XIII: Verification and evaluation

## 81. Verification principle

Do not rely on “looks good,” “seems to work,” or a passing build. Every hard part needs an evaluation surface.

## 82. Test layers

### Unit tests

- state-machine transitions;
- provenance changes;
- review-token invalidation;
- placement classification;
- text fitting;
- answer-page rendering decisions;
- semantic-mapper output validation;
- retry and idempotency behavior.

### Contract tests

- OpenAPI request and response shapes;
- generated frontend client compatibility;
- Structured Outputs schema;
- Realtime tool payloads;
- GCS manifest serialization;
- stable error codes.

### PDF corpus tests

For every accepted fixture:

- expected question count;
- exact source text;
- stable source order;
- expected placement outcome;
- no answer overlap;
- minimum font size;
- exact approved text in output;
- source object unchanged;
- final file opens in Chrome and Adobe Acrobat Reader, with an automated parser-level proxy and documented manual check.

### Integration tests

- upload through persisted assignment;
- candidate creation and rephrase;
- review and confirmation;
- revision and reconfirmation;
- export and download;
- assignment version conflict;
- expired or replayed review token;
- Realtime credential authorization.

### Browser tests

- direct typed path;
- guided path with fake Realtime events;
- live direct voice path where environment permits;
- wording comparison;
- inline placement;
- attached answer page;
- microphone denied;
- Realtime disconnect;
- keyboard-only completion;
- mobile worksheet modal;
- export download.

### Accessibility tests

- Storybook accessibility addon;
- Playwright axe scan;
- keyboard traversal;
- focus restoration after dialogs;
- live-region behavior;
- reduced motion;
- text zoom at 200 percent;
- mobile viewport with no horizontal scrolling.

## 83. Visual screenshot matrix

Capture from the running app, not design software:

| State | Desktop | Tablet | Mobile |
|---|---:|---:|---:|
| Upload | yes | no | yes |
| Document checking | yes | no | yes |
| Worksheet ready | yes | no | yes |
| Question choice | yes | yes | yes |
| Direct listening | yes | no | yes |
| Direct captured | yes | no | yes |
| Guided conversation | yes | yes | yes |
| Wording comparison | yes | no | yes |
| Exact review inline | yes | no | yes |
| Exact review appendix | yes | no | yes |
| Answer added | yes | no | yes |
| Worksheet review | yes | yes | yes |
| Export complete | yes | no | yes |
| Unsupported PDF | yes | no | yes |
| Voice unavailable | yes | no | yes |

Suggested viewports:

- desktop: 1440x1000;
- tablet: 1024x1366;
- mobile: 390x844.

Store screenshots under `artifacts/v2/screenshots/`.

## 84. Visual quality scorecard

Score each completed screen set out of 100:

| Category | Points | Failure examples |
|---|---:|---|
| Product hierarchy | 20 | PDF or chrome overwhelms the active question; multiple competing primary actions. |
| Component consistency | 15 | Mixed radii, control heights, icon styles, or base component systems. |
| Legibility and accessibility | 20 | Tiny labels, weak contrast, narrow transcript, unclear focus. |
| PDF authenticity | 15 | Fake HTML worksheet, distorted page, irrelevant toolbar, inaccurate overlays. |
| State clarity | 15 | Voice state or candidate provenance is ambiguous; review looks like ordinary chat. |
| Responsive behavior | 10 | Task appears after PDF on mobile; horizontal overflow; cramped comparison. |
| Restraint and credibility | 5 | Fake telemetry, unsupported claims, decorative complexity, generic AI glow. |

Gate threshold:

- total score at least 90;
- no category below 80 percent of its available points;
- zero critical accessibility defects;
- zero anti-reference violations.

The lead performs an initial score. A read-only visual-review subagent performs a second score. Resolve disagreements through browser evidence and update the screen.

## 85. Performance budgets

Measure before claiming success.

Initial P0 targets:

- marketing page usable on a normal broadband connection without loading the PDF stack;
- app shell interactive before a document is loaded;
- PDF viewer loaded only on app routes or when needed;
- no giant PDF or Realtime bundle in the landing-page entry chunk;
- direct typed workflow works without OpenAI Realtime loading;
- page transitions remain responsive on a mid-range laptop;
- no unbounded conversation DOM growth;
- PDF analysis exposes timeout and cancellation behavior;
- export completes within Cloud Run's configured request or job limits for the corpus.

Record bundle sizes and measured timings in `artifacts/v2/performance.md`.

## 86. Required evidence bundle

A phase is not complete without evidence. Final bundle:

```text
artifacts/v2/
  screenshots/
  pdfs/
    source/
    completed/
  test-results/
  accessibility/
  performance.md
  visual-scorecard.md
  manual-test-checklist.md
  demo-script.md
  final-summary.md
```

---

# Part XIV: Implementation phases and gates

## 87. Phase 0: Audit and plan

### Work

Run the six read-only audits, establish source hierarchy, inspect git history, select migration boundaries, and create OpenSpec artifacts.

### Gate 0

Required:

- baseline build and tests recorded;
- current app screenshots captured;
- `BASELINE_AUDIT.md` complete;
- `CONFLICTS.md` complete;
- architecture decisions complete;
- dependency plan complete;
- task graph with file ownership complete;
- no production code changed.

## 88. Phase 1: V2 foundation and design-system integration

### Work

- create V2 branch or worktree;
- add Untitled UI theme and only required components;
- add semantic Claros token layer;
- add application providers;
- add new route shell;
- add EmbedPDF proof-of-integration with a real sample;
- add Storybook and MSW V2 fixtures;
- preserve legacy route.

### Parallelism

Allow one frontend agent to integrate Untitled UI and one read-only agent to validate available components. Only the lead changes dependencies and shared tokens.

### Gate 1

Required:

- app builds;
- legacy tests still pass or documented migration tests replace them;
- no second visible component system in V2;
- real PDF renders;
- basic keyboard navigation works;
- screenshot of the empty shell passes a preliminary visual review;
- no fake worksheet HTML.

## 89. Phase 2: Complete fixture-driven UI

### Work

Implement every P0 screen and transition with deterministic fixture data and a fake Realtime adapter. Do not connect live OpenAI yet.

### Gate 2

Required:

- both paths complete end to end with fixtures;
- exact review mandatory;
- inline and appendix outcomes visible;
- mobile flow complete;
- Storybook states complete;
- Playwright flows pass;
- axe passes;
- screenshot matrix complete for fixture states;
- visual score at least 90;
- no live model dependency.

## 90. Phase 3: FastAPI, GCS, and document engine

### Work

- establish FastAPI `/api/v2` service;
- implement signed anonymous assignment access;
- implement GCS object layout and manifests;
- implement preflight;
- implement physical IR;
- implement deterministic geometry;
- implement overlay and answer-page export;
- implement gold corpus and tests;
- wire frontend to MSW-compatible API contracts.

### Parallelism

PDF extraction and frontend API client work may run in parallel only after OpenAPI schemas are frozen. Shared schemas remain lead-owned.

### Gate 3

Required:

- all accepted fixtures parse deterministically;
- all rejected fixtures fail with expected codes;
- source objects remain unchanged;
- output preserves exact confirmed text;
- no overlap or sub-floor text;
- attached pages work;
- API integration tests pass;
- app can complete typed flow against real backend;
- Cloud Run-compatible container builds.

## 91. Phase 4: OpenAI semantic mapping and rephrasing

### Work

- implement strict Structured Outputs schemas;
- implement block-ID semantic mapping;
- implement post-model validation;
- implement ambiguous-response rejection;
- implement optional rephrasing with provenance;
- add recorded or mocked provider responses for deterministic tests;
- evaluate model choice against corpus.

### Gate 4

Required:

- exact question text reconstructed from source blocks;
- no output coordinate accepted from model;
- malformed, refused, or ambiguous model output handled safely;
- quality report includes per-fixture result and latency/cost observations;
- rephrasing never silently replaces the candidate;
- typed end-to-end workflow passes against real semantic mapping.

## 92. Phase 5: OpenAI Realtime

### Work

- implement ephemeral credential endpoint;
- implement `RealtimeAgent` and `RealtimeSession` adapter;
- connect direct mode;
- connect guided mode;
- connect captions and interruptions;
- connect narrow tools;
- implement exact-state voice confirmation;
- implement failure and reconnect behavior;
- keep fake adapter for tests.

### Gate 5

Required:

- direct voice answer works;
- guided reasoning works;
- transcript and candidate cannot diverge silently;
- exact review still mandatory;
- casual agreement cannot confirm;
- disconnect preserves draft;
- typed fallback works without Realtime;
- no standard API key reaches browser;
- browser tests pass with fake adapter;
- documented manual live-voice test passes.

## 93. Phase 6: Cutover and production hardening

### Work

- connect all real APIs;
- remove dead V2 mock adapters from production bundles;
- migrate `/app` to V2;
- move legacy route behind explicit development-only access or remove it after evidence capture;
- remove unused Radix, `react-pdf`, and old server dependencies only when no remaining route requires them;
- finalize CI and Cloud Run deployment;
- run dependency and security checks;
- complete accessibility and performance passes.

### Gate 6

Required:

- clean production build;
- deployment smoke tests pass;
- no sample-hash-only restriction remains in V2;
- no assignment state depends on in-memory maps;
- no dead competing UI foundation remains in production V2;
- final screenshot matrix passes 90-point threshold;
- all P0 acceptance criteria pass.

## 94. Phase 7: Demo and submission package

### Work

- choose the strongest biology fixture;
- seed or prepare a deterministic live demo path;
- record a two to three minute demo;
- generate final completed PDF;
- create technical summary;
- create README setup and architecture section;
- document exact supported scope honestly.

### Gate 7

Required:

- deployed URL passes smoke check;
- demo can be repeated from a clean browser session;
- both answer paths and both placement outcomes have evidence;
- final PDF opens correctly;
- submission copy contains no unsupported claim;
- `artifacts/v2/final-summary.md` lists commands, results, known limitations, and remaining risks.

---

# Part XV: Git, review, and change control

## 95. Branching

Create a dedicated branch or worktree such as:

```text
codex/claros-v2-nerdy
```

Do not work directly on `main` until the V2 gates pass.

## 96. Checkpoints

Commit at meaningful gates, not after every tiny edit. Suggested checkpoints:

1. audit and OpenSpec plan;
2. Untitled UI and route shell;
3. fixture-driven V2 workflow;
4. real document engine and APIs;
5. semantic mapping;
6. Realtime integration;
7. hardening and cutover;
8. final demo evidence.

Each commit must build or clearly state why it is a planning-only commit.

## 97. Destructive-action prohibition

Do not:

- hard reset;
- force push;
- rewrite history;
- delete working historical evidence before replacement;
- remove all tests and replace them with shallow snapshots;
- disable checks to make CI green;
- accept a visual regression because the build passes;
- restore an old branch wholesale;
- install a second component kit to fill one missing component;
- create undocumented manual production steps.

## 98. Review protocol

At every gate:

1. run the exact commands;
2. capture output;
3. inspect browser screenshots;
4. inspect changed files and dependency diff;
5. update decisions, risks, and status;
6. run a read-only review subagent focused on regressions and contract violations;
7. fix critical findings before continuing.

---

# Part XVI: Definition of done

## 99. P0 product acceptance

The product is done only when all of these are true:

- a student can upload or open a supported real PDF;
- Claros grounds questions to exact source evidence;
- the student can answer directly by voice or typing;
- the student can use guided reasoning by voice or typing;
- the student can request and compare a clearer wording suggestion;
- exact review is mandatory;
- voice confirmation works only in exact review with the exact command;
- approved text is preserved exactly;
- safe answers appear inline;
- unsafe or long answers appear on attached answer pages;
- source PDF remains unchanged;
- revisions require reconfirmation;
- the final derivative PDF downloads and opens;
- microphone and Realtime failures preserve progress;
- keyboard-only completion works;
- the deployed UI uses Untitled UI consistently;
- the actual PDF is rendered through EmbedPDF;
- the V2 UI contains no generated design-board artifacts or fake claims;
- the full evidence bundle exists;
- all gates pass.

## 100. Engineering acceptance

- production build succeeds;
- unit, contract, integration, E2E, PDF, and accessibility tests pass;
- no high-severity dependency issue is silently ignored;
- API keys and GCS objects are protected;
- assignment state survives Cloud Run instance replacement;
- source and export objects are immutable by path and generation policy;
- model output is validated after schema validation;
- no model controls geometry or approval;
- CI runs the required checks;
- README and architecture docs match the implemented system.

## 101. Visual acceptance

- score at least 90/100;
- no category below 80 percent;
- no tiny operational labels;
- no fake PDF;
- no equal 50/50 split;
- no enterprise dashboard aesthetic;
- no generic chatbot layout;
- no base controls hand-built outside Untitled UI;
- task is first on mobile;
- review is visually distinct from transcript;
- actual browser screenshots demonstrate the result.

## 102. Honest limitations

The final public product may say:

- supports native-text sequential short-answer PDFs;
- starts with secondary-school worksheets;
- scans and complex layouts are not supported yet;
- answers may use an attached page when they cannot fit safely.

It may not imply universal compatibility, certification, institutional adoption, or integrations that are not implemented.

---

# Part XVII: Final directive to Sol Ultra

Treat this as a long-running engineering program with explicit evaluation, not a single-pass code-generation task.

Start with the six read-only audits. Synthesize the result. Do not edit production code until Gate 0 is complete. After Gate 0, execute one phase at a time. Use subagents for independent investigation and review, but keep shared contracts and overlapping writes under one lead. Do not declare completion without browser evidence, exported PDFs, and passing gates.

The implementation decision is settled:

```text
Untitled UI React for ordinary visible UI
EmbedPDF for actual PDF rendering
FastAPI plus GCS for the production backend and persistence
Python deterministic PDF engine
OpenAI Responses with Structured Outputs for semantic block mapping
OpenAI Agents SDK Realtime over WebRTC for voice
XState for visible workflow
TanStack Query for server state
Motion only for bounded product transitions
Storybook, MSW, Playwright, axe, and the gold PDF corpus for evaluation
```

Do not use Opensource UI. Do not generate another visual-reference board. Build the real product, inspect it in the browser, score it, and iterate until the evidence satisfies this PRD.
