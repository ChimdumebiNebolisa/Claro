## Purpose

Defines how server-owned physical evidence produces repeatable inline,
attached-answer-page, or rejection outcomes without model or client geometry.

## ADDED Requirements

### Requirement: Server-owned placement authority
Only deterministic backend code operating on validated physical IR MAY produce
placement evidence. Model output and browser input MUST NOT supply, edit, or
authorize coordinates. Browser overlay bounds MUST be a display projection of a
server decision and MUST NOT become export truth.

#### Scenario: Client changes overlay coordinates
- **WHEN** a browser submits or tampers with display geometry
- **THEN** the server ignores or rejects it and derives placement solely from stored physical evidence

### Requirement: Canonical coordinate system
Stored display geometry MUST use crop-relative, top-left integer milli-points
with page media box, crop box, rotation, user unit, and affine transform
recorded. Conversion to a PDF renderer's bottom-left coordinates MUST occur only
through tested deterministic transforms.

#### Scenario: Identity page is converted for rendering
- **WHEN** an inline box from a zero-rotation default-crop page is rendered
- **THEN** the tested affine transform produces finite, in-bounds renderer coordinates that round-trip to the canonical box

### Requirement: Placement priority and outcomes
The resolver MUST evaluate safe writable form fields, rectangular boxes,
answer-line groups, and bounded whitespace in that order, then use an attached
answer page. Its only outcomes MUST be `inline`, `appendix`, or `reject`.
Grounded questions with missing, competing, or insufficient inline regions MUST
use `appendix`; `reject` is reserved for unsafe question/context grounding.

#### Scenario: Form field is safely writable
- **WHEN** one verified compatible text form field belongs to the grounded question and can fit the answer
- **THEN** the resolver selects that field before other inline candidates

#### Scenario: Multiple plausible regions compete
- **WHEN** the question is grounded but no single inline candidate is safely authoritative
- **THEN** the resolver selects `appendix` rather than guessing or rejecting the question

#### Scenario: Question grounding is unsafe
- **WHEN** exact question or required context evidence cannot be validated
- **THEN** the resolver returns `reject` and no review token can be issued

### Requirement: Deterministic readable fitting
The resolver MUST preserve exact approved text, wrap only at word boundaries or
explicit newlines, begin at 12pt, stop at a 10pt floor, apply 1.2 line leading
and configured padding, and reject any inline fit that crosses its box or
collides with source content or another answer. Fit MUST be proven on a scratch
surface before review.

#### Scenario: Answer fits at a readable size
- **WHEN** exact text fits wholly within one authorized region at 10pt or larger with no collision
- **THEN** the resolver returns a stable inline plan with the proven font, lines, and bounds

#### Scenario: Answer cannot fit readably
- **WHEN** exact text would require clipping, overlap, truncation, or text smaller than 10pt
- **THEN** the resolver returns an appendix plan without changing the text

### Requirement: Conservative transformed-page handling
For P0, non-identity rotation or crop-box transforms MUST use appendix placement
unless the checksum-pinned gold corpus proves extraction, display, fitting, and
export transforms end to end for that exact class. Unproven transforms MUST NOT
be guessed.

#### Scenario: Rotated page lacks proven transform support
- **WHEN** a grounded question is on a page whose transform class is not corpus-approved
- **THEN** Claros offers attached-answer-page placement and does not emit an inline box

### Requirement: Reproducible placement evidence
A placement plan MUST bind physical-IR version, question evidence, exact text
hash, algorithm version, outcome, region or appendix data, fit evidence, and a
stable placement hash. Equivalent inputs MUST produce equivalent plans.

#### Scenario: Placement is recomputed before export
- **WHEN** source, IR, algorithm, question, and exact answer are unchanged
- **THEN** recomputation yields the same outcome and placement hash used during review

#### Scenario: Placement inputs changed
- **WHEN** any bound source, IR, algorithm, evidence, or answer value differs
- **THEN** the prior review is stale and Claros requires a fresh placement review
