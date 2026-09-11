## Purpose

Defines which native-text short-answer worksheets Claros may expose as ready,
how grounded questions are represented, and how unsupported files fail safely.

## ADDED Requirements

### Requirement: Bounded native-text admission
Claros MUST validate PDF content rather than filename alone and MUST accept for
analysis only readable native-text PDFs no larger than 10 MiB, containing one
to eight pages and no more than 40 supported sequential short-answer questions.
Encrypted, password-protected, malformed, scan-only, or out-of-limit documents
MUST NOT become ready assignments.

#### Scenario: Supported native-text worksheet enters analysis
- **WHEN** a readable PDF is within the byte and page limits and contains selectable text
- **THEN** Claros creates an owner-bound analyzing assignment and evaluates the complete document

#### Scenario: Scanned worksheet is rejected
- **WHEN** a PDF contains no sufficient machine-readable question text
- **THEN** Claros returns `requires_ocr`, explains that scans are unsupported, and offers another upload or the official sample

#### Scenario: Limit violation is rejected
- **WHEN** the upload exceeds a byte, page, extracted-text, or supported-question limit
- **THEN** Claros returns the corresponding stable limit code without fabricating a partial ready assignment

### Requirement: Whole-document readiness
Claros MUST evaluate every page before reporting an assignment ready. A ready
assignment MUST contain only source-ordered, grounded short-answer questions and
MUST include student-safe warnings for understood questions whose context or
placement requires special handling.

#### Scenario: Complete analysis becomes ready
- **WHEN** every exposed question is grounded to valid source evidence and the supported-question count is within limits
- **THEN** Claros reports the assignment ready with exact source order, page count, question count, and safe placement summary

#### Scenario: Ambiguous question structure rejects safely
- **WHEN** the system cannot distinguish required question boundaries or ground necessary context without invention
- **THEN** Claros reports a stable rejected state and exposes no fabricated question

### Requirement: Inline space is not required for acceptance
A grounded short-answer question MUST remain supported when no safe inline
answer region exists. Claros MUST designate attached-answer-page eligibility in
that case; it MUST reject only when the question or necessary context cannot be
grounded safely.

#### Scenario: Grounded question has no writable region
- **WHEN** exact question evidence is valid but deterministic geometry finds no safe readable inline region
- **THEN** the assignment remains supported and the question is eligible for attached-answer-page placement

### Requirement: Exact source question contract
Every question MUST reference validated physical block IDs and MUST reconstruct
its visible wording exactly from those blocks and their recorded joiners. The
system MUST preserve source page and reading order and MUST NOT paraphrase,
complete, or reorder the source question.

#### Scenario: Multi-block prompt is exposed
- **WHEN** a supported question spans multiple physical text blocks
- **THEN** Claros reconstructs one exact prompt from the selected blocks in physical reading order

#### Scenario: Returned evidence is invalid
- **WHEN** a semantic mapping contains an unknown, duplicate, overlapping, or out-of-order source block ID
- **THEN** Claros rejects the mapping rather than exposing an inferred question

### Requirement: Stable rejection and recovery
Every unsupported result MUST include a stable machine-readable error code, a
student-safe explanation of what is unsupported, a recoverable flag, and an
action to try another file or use the official sample. Provider confidence,
coordinates, parser telemetry, and raw exception text MUST NOT be exposed.

#### Scenario: Unsupported document reaches the browser
- **WHEN** preflight or grounding rejects an upload
- **THEN** the UI receives the stable error envelope and presents an actionable explanation without internal diagnostics

### Requirement: Safe assignment projection
The student projection MUST include only assignment status, source metadata,
ordered exact questions, current answers, safe warnings, and backend-verified
display context needed for the workflow. It MUST NOT expose credentials, storage
internals, review-token contents, model prompts, or client-authoritative geometry.

#### Scenario: Ready assignment is fetched
- **WHEN** its authorized owner requests the assignment
- **THEN** Claros returns the current version and safe workflow projection without secret or unvalidated fields
