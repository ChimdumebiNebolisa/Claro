## Purpose

Defines deterministic physical PDF evidence and closed-world semantic mapping
that grounds exact, ordered worksheet questions without model-owned geometry.

## ADDED Requirements

### Requirement: Deterministic physical document IR
For a given source generation and parser version, Claros MUST produce
byte-identical canonical physical IR. The IR MUST record source hash, page
media/crop boxes, rotation, user unit, affine transform, exact UTF-8 content,
reading order, ambiguity flags, and physical blocks of kind `text`, `line`,
`rect`, `form_field`, or `image`.

#### Scenario: Source is parsed repeatedly
- **WHEN** the same PDF bytes are parsed multiple times with the same engine and configuration
- **THEN** the canonical serialized physical IR and its content hash are identical

#### Scenario: Malformed physical value is encountered
- **WHEN** a block box, page transform, dimension, or order value is non-finite or out of page bounds
- **THEN** Claros rejects the document with a stable physical-evidence error rather than storing unsafe IR

### Requirement: Stable source-derived block identity
Every physical block MUST have a stable identifier derived from immutable
document, page, kind, order, exact content, and box evidence. A block identifier
MUST NOT depend on a provider response or mutable browser state.

#### Scenario: A fixture is reparsed
- **WHEN** source bytes and parser version are unchanged
- **THEN** every corresponding physical block retains the same stable identifier

### Requirement: Explicit exact-text reconstruction
Text blocks MUST preserve their exact string and an explicit
`join_after` value of `none`, `space`, or `newline`. Question wording MUST be
reconstructed only by ordering validated selected blocks and applying those
joiners; the semantic model MUST NOT supply replacement question text.

#### Scenario: Prompt spans lines and blocks
- **WHEN** validated prompt IDs select multiple text blocks
- **THEN** code reconstructs the exact source prompt deterministically, including recorded spacing and line breaks

### Requirement: Closed-world semantic mapping
The semantic mapper MUST receive only stable block IDs, exact text, block kind,
page, reading order, and bounded deterministic relation hints. Its strict output
MUST identify ordered question keys, prompt and context block IDs, supported
question type, visual-context dependency, and warnings. It MUST NOT return or
control coordinates, rewritten prompts, placement, confirmation, or export.

#### Scenario: Model returns a valid mapping
- **WHEN** every selected ID exists, source order and overlap rules hold, and each question is a supported short answer
- **THEN** Claros creates exact questions from physical evidence without using any model-authored geometry or wording

#### Scenario: Model returns coordinates or unknown IDs
- **WHEN** provider output contains a forbidden coordinate field or references an ID absent from the request
- **THEN** Claros rejects the entire provider result and exposes no fabricated question

### Requirement: Post-schema semantic validation
Schema validity alone MUST NOT make a mapping trusted. Claros MUST reject
duplicate, overlapping, reordered, ungrounded, unsupported, ambiguous, refused,
timed-out, malformed, or incomplete mappings using stable internal outcomes and
student-safe errors.

#### Scenario: Two questions claim the same prompt evidence
- **WHEN** provider output overlaps source blocks in a way not permitted by shared-instruction rules
- **THEN** post-validation rejects the mapping rather than guessing ownership

#### Scenario: Provider is unavailable
- **WHEN** semantic mapping times out, refuses, or returns malformed output
- **THEN** the assignment enters a recoverable analysis failure without exposing provider content or inventing structure

### Requirement: Corpus-gated document understanding
Parser and mapper changes MUST be evaluated against a checksum-pinned corpus
covering biology, middle-school science, a non-science worksheet, blank lines,
boxes, multi-page order, long-answer fallback, Unicode, rotation or non-default
crop box, no safe inline region, scan rejection, and ambiguous-boundary
rejection. Accepted cases MUST assert exact question count/text/order; rejected
cases MUST assert stable codes.

#### Scenario: Document-understanding behavior changes
- **WHEN** parser, prompt, schema, model default, or post-validation changes
- **THEN** all required corpus cases run repeatedly and publish per-fixture deterministic results before the change advances

### Requirement: Semantic model selection is measured
Claros MUST evaluate configured semantic models in the fixed order
`gpt-5.6-luna`, `gpt-5.6-terra`, and `gpt-5.6-sol` and MUST select the first
candidate achieving 100 percent required-gold correctness, zero invalid IDs over
three runs, and the recorded latency threshold. Production calls MUST disable
provider storage and tools.

#### Scenario: First candidate misses a required case
- **WHEN** `gpt-5.6-luna` fails correctness, ID, or latency acceptance
- **THEN** Claros evaluates the next configured candidate and records the evidence without weakening corpus expectations
