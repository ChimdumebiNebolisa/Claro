## Purpose

Defines generation and authorized delivery of a usable derivative PDF from an
immutable source and the assignment's current confirmed answer revisions.

## ADDED Requirements

### Requirement: Export current confirmed answers only
Export MUST be available after at least one answer is confirmed. It MUST include
the latest confirmed revision for each answered question and MUST exclude
drafts, review snapshots, suggestions not selected and confirmed, tutoring
turns, transcripts, and unanswered questions. Unanswered worksheet regions MUST
remain blank.

#### Scenario: Assignment is partially complete
- **WHEN** at least one question is confirmed and other questions are unanswered
- **THEN** Claros creates a derivative containing only the confirmed answers and preserves the unanswered source regions

#### Scenario: No answer is confirmed
- **WHEN** export is requested before any confirmed answer exists
- **THEN** Claros returns a recoverable `no_confirmed_answers` error and creates no derivative

### Requirement: Immutable source derivative
The exported file MUST clone the exact immutable source generation in original
page order and add only validated answer overlays and appended answer pages. It
MUST never overwrite the stored source, reconstruct source pages, white out
source content, or publish to the source object path.

#### Scenario: Derivative export succeeds
- **WHEN** all source and placement evidence revalidates
- **THEN** the stored source bytes and generation remain unchanged and a new immutable export object is created

### Requirement: Exact Unicode output
Every rendered answer MUST preserve the exact approved Unicode string. Export
MUST NOT paraphrase, truncate, replace punctuation, transliterate to ASCII, or
otherwise alter text to make it fit. The renderer MUST use an embedded font
that covers every accepted glyph.

#### Scenario: Unicode answer is exported
- **WHEN** a confirmed answer contains supported accents, curly punctuation, symbols, or non-ASCII names
- **THEN** parser extraction and visual inspection recover the exact approved string from the derivative

#### Scenario: Required glyph is unsupported
- **WHEN** the configured embedded font cannot render a candidate glyph safely
- **THEN** review or export fails explicitly without changing the confirmed answer or emitting substituted text

### Requirement: Approved placement is revalidated
Before rendering, export MUST reload the immutable source generation and verify
each confirmed answer's question evidence, exact-text hash, placement hash,
bounds, collision result, and readable size. A changed or unsafe result MUST
fail and require fresh review rather than silently moving the answer.

#### Scenario: Source generation changed
- **WHEN** the source hash or object generation differs from the reviewed evidence
- **THEN** export returns a stable stale-source error and publishes no derivative

#### Scenario: Placement no longer validates
- **WHEN** current deterministic evidence cannot reproduce the reviewed inline or appendix decision
- **THEN** export identifies the affected question and requires a new review without losing confirmed state

### Requirement: Readable inline rendering
Inline answers MUST remain inside the validated region, avoid source-content and
answer collisions, wrap at word boundaries, and use no text smaller than 10pt.
An answer that cannot meet every constraint MUST have been reviewed for an
attached answer page instead; it MUST never be squeezed or clipped inline.

#### Scenario: Confirmed inline answer fits
- **WHEN** the exact text fits at or above 10pt with required padding and no collision
- **THEN** the derivative renders that answer wholly inside the approved region

### Requirement: Complete attached answer pages
Attached answer pages MUST paginate without truncation and MUST include the
worksheet title, stable question number or identifier, exact source question,
source page number, and exact approved answer for every appendix decision.

#### Scenario: Long answer uses an appendix
- **WHEN** a confirmed answer was reviewed with attached-answer-page placement
- **THEN** the derivative retains all source pages and appends a readable, fully labeled entry containing the complete exact answer

### Requirement: Idempotent authorized export
For one assignment version, repeated export creation MUST return the same
export identity and immutable bytes. A different assignment version MUST use a
different export identity. Status and download MUST enforce owner authorization,
and failure or retry MUST preserve confirmed answers.

#### Scenario: Export request is repeated
- **WHEN** the owner repeats export for an unchanged assignment version
- **THEN** Claros returns the existing export result without rendering or publishing a second conflicting object

#### Scenario: Another owner requests the download
- **WHEN** a session not bound to the assignment requests export status or bytes
- **THEN** Claros denies access without revealing whether the object exists

### Requirement: Final PDF validation
Before an export becomes downloadable, Claros MUST validate PDF openability,
expected source-page count and order, appendix count, exact answer text,
finite/in-bounds placements, minimum text size, and source immutability. A
validation failure MUST leave no published successful export.

When OpenPDF is selected, rendering MUST run in a bounded process and the
quarantined derivative MUST pass qpdf structural checks plus an independent
PDFBox validation process before publication. A missing Java worker, font, or
qpdf dependency MUST fail startup rather than fall back to another renderer.
PDF.js compatibility MAY run after publication in CI or release verification,
but MUST NOT add a browser launch to the synchronous application request.

#### Scenario: Generated bytes fail validation
- **WHEN** any structural, text, page, bounds, or source-integrity assertion fails
- **THEN** the export enters a recoverable failed state and no success download is exposed

#### Scenario: OpenPDF runtime dependency is unavailable
- **WHEN** OpenPDF is explicitly selected and Java 21+, its worker JAR, the allowlisted font, or qpdf is unavailable
- **THEN** Claros fails startup with a dependency diagnostic and does not silently select another renderer

#### Scenario: Independent validator fails
- **WHEN** qpdf or PDFBox rejects the quarantined OpenPDF derivative
- **THEN** Claros deletes the quarantined output, preserves confirmed answers, and exposes no successful export
