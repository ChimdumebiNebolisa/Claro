## Purpose

Defines the question-first, responsive, accessible student experience from
worksheet upload through exact review, answer revision, and PDF download.

## ADDED Requirements

### Requirement: Truthful upload and readiness flow
The workspace MUST expose distinct upload, document-checking, rejected, and
worksheet-ready states. Client checks MUST validate file type and size promptly,
while server validation remains authoritative. Progress MUST be event-derived;
when stages are unavailable the UI MUST show an indeterminate message rather
than invented percentages.

#### Scenario: Student uploads a worksheet
- **WHEN** a file passes the immediate browser checks
- **THEN** the UI submits it, announces analysis, and displays only backend-reported stages or one truthful indeterminate state

#### Scenario: Worksheet is ready
- **WHEN** analysis completes successfully
- **THEN** the UI shows title, page count, supported-question count, safe warnings, `Start Question 1`, and `View worksheet`

### Requirement: Question-first responsive hierarchy
The active question MUST precede source context in reading and DOM order and
MUST remain the primary task at every viewport. Desktop MUST use a task-first
workspace with a fixed supporting source pane and no required resizer. Tablet
MUST stack source after task. Mobile MUST expose the full worksheet through a
keyboard-accessible full-screen dialog while leaving the question first.

#### Scenario: Desktop question is opened
- **WHEN** the viewport is at least 1180 CSS pixels wide
- **THEN** the exact question and task occupy the primary column and the actual source appears in a 400–440px supporting pane

#### Scenario: Mobile worksheet is opened
- **WHEN** the student invokes `View worksheet` below 768 CSS pixels
- **THEN** an accessible full-screen dialog renders the actual source, traps focus, and restores focus to the invoking control when closed

### Requirement: Two equal entry paths
Every unanswered question MUST initially show `Say my answer` and
`Help me think it through` with equal visual weight and no preselection or
recommendation. Both paths MUST preserve the exact question and converge on the
same candidate comparison, review, confirmation, revision, and export rules.

#### Scenario: Unanswered question receives focus
- **WHEN** the question-choice state becomes active
- **THEN** both entry paths, `Type instead`, and `View worksheet` are understandable and keyboard reachable without onboarding

### Requirement: Complete typed operation
Typed input MUST complete both direct and guided paths at every voice state,
including when microphone permission or Realtime fails. Failure MUST preserve
the candidate and relevant conversation state and MUST NOT require upload or
page reload.

#### Scenario: Microphone is unavailable
- **WHEN** permission is denied before or during an answer
- **THEN** the UI announces `Microphone unavailable`, preserves current text, and offers immediate `Continue by typing`

#### Scenario: Guided voice disconnects
- **WHEN** the Realtime connection is lost after guided turns exist
- **THEN** the UI preserves the bounded transcript and candidate and allows the student to finish the final answer by typing

### Requirement: Distinct comparison and exact-review states
Rough transcript, tutoring turns, wording comparison, and exact review MUST be
visually and semantically distinct. Mobile comparison MUST stack selectable
versions. Exact review MUST expose `Hear it`, destination, `Change answer`, and
`Use this exact answer` as its dominant action and MUST not expose internal
placement or token terminology.

#### Scenario: Student requests a rephrase
- **WHEN** a safe suggestion is available
- **THEN** the UI shows `Your words` and `Suggested wording` simultaneously with non-color selection state before entering exact review

#### Scenario: Exact review is announced
- **WHEN** a fresh review snapshot loads
- **THEN** focus and screen-reader structure identify the exact-review heading, exact text, provenance, destination, and explicit actions

### Requirement: Answer review and partial export flow
The worksheet review MUST list questions in source order with answered or
unanswered state, concise confirmed-answer preview, destination, edit, and
jump-to-question actions. It MUST offer export after at least one answer is
confirmed and MUST leave unanswered questions blank.

#### Scenario: One of several questions is confirmed
- **WHEN** the student opens worksheet review
- **THEN** the confirmed answer and remaining unanswered questions are distinguishable and `Download completed PDF` is available

### Requirement: Accessible and restrained interaction
The complete workflow MUST support keyboard, pointer, touch, semantic labels,
visible focus, at least 44x44px primary targets, captions, text voice states,
mute without lost text, no color-only meaning, no forced answering timeout,
200 percent text zoom, and reduced motion with equivalent live-region updates.
No required action may depend on dragging or resizing.

#### Scenario: Keyboard-only completion
- **WHEN** a student uses only keyboard navigation and typed input
- **THEN** upload, path selection, answering, comparison, review, confirmation, revision, export, download, and dialogs remain operable and understandable

#### Scenario: Reduced motion is requested
- **WHEN** the operating system reports reduced-motion preference
- **THEN** placement and question transitions update immediately and announce the resulting state without essential animation

### Requirement: Honest marketing surface
The public route MUST explain direct and guided paths, exact approval, source
preservation, accessibility, supported-PDF limits, and the final CTA using an
authentic screenshot or live preview of the implemented product. It MUST NOT
publish fabricated metrics, customers, pricing, certifications, integrations,
institutional claims, or an HTML recreation presented as a worksheet.

#### Scenario: Marketing page loads
- **WHEN** a visitor opens `/`
- **THEN** the prescribed Claros navigation and product promise appear without loading PDF or Realtime runtime bundles

### Requirement: Same-browser restoration
An unexpired anonymous assignment MUST restore through a server-managed signed
session when the same browser reloads a V2 assignment URL. No assignment bearer
secret may be stored in `localStorage` or `sessionStorage`.

#### Scenario: Authorized assignment reloads
- **WHEN** the browser revisits an assignment with its valid owner session
- **THEN** Claros restores current version, confirmed answers, candidate state, and the active or next incomplete question
