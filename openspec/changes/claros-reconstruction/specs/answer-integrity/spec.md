## Purpose

Defines candidate provenance, visible wording choice, mandatory exact review,
answer-bound confirmation, revision, and exact Unicode preservation.

## ADDED Requirements

### Requirement: One exact candidate source
Each question MUST have one current candidate whose exact Unicode text and
version are shared by transcript, editor, comparison, and review projections.
Claros MUST NOT silently lowercase, correct, paraphrase, trim, normalize, or
replace that string after the student has selected or edited it.

#### Scenario: Student edits a candidate
- **WHEN** the student changes capitalization, whitespace, punctuation, symbols, apostrophes, or accented characters
- **THEN** every later review and confirmed-answer projection contains that exact edited string

#### Scenario: Voice transcript updates the draft
- **WHEN** a direct voice turn produces student text
- **THEN** the editable field and transcript label project the same candidate version rather than divergent copies

### Requirement: Validated candidate provenance
Every candidate MUST have exactly one internal origin from
`student_verbatim`, `student_normalized`, `claros_rephrase`,
`student_after_guidance`, or `student_edited`. The server MUST derive or validate
origin against the interaction evidence and MUST reject impossible or
client-forged transitions. The UI MUST expose only `Your words` or
`Suggested wording`.

#### Scenario: Student edits suggested wording
- **WHEN** the student changes any text in a selected Claros suggestion
- **THEN** the new candidate origin is `student_edited` and the visible label is `Your words`

#### Scenario: Client submits impossible provenance
- **WHEN** a request claims `claros_rephrase` without a valid server rephrase result
- **THEN** the server rejects the candidate origin and preserves the prior candidate

### Requirement: Opt-in wording comparison
Claros MUST create a rephrasing only after `Make it clearer` is requested. It
MUST preserve the current student-derived version, display both versions with
distinct labels, require an explicit selection, and reject a suggestion that
adds an unsupported factual claim. Selection alone MUST NOT confirm the answer.

#### Scenario: Safe suggestion is returned
- **WHEN** the student requests clearer wording and the factual-delta check finds no unsupported claim
- **THEN** both exact versions remain visible and the student can explicitly keep their wording or select the suggestion

#### Scenario: Suggestion adds a factual claim
- **WHEN** the generated suggestion contains information not present in the candidate or allowed context
- **THEN** Claros rejects or flags the suggestion without replacing the current candidate

### Requirement: Mandatory exact review
No candidate may become confirmed until the UI presents a fresh server review
snapshot containing the exact candidate text, `Your words` or
`Suggested wording`, and either `Your answer fits on the original worksheet.`
or `This answer will appear on an attached answer page.` The review MUST use the
heading `Review your exact answer`, the instruction `Read every word before it
reaches the worksheet.`, and the primary action `Use this exact answer`.

#### Scenario: Draft has not been reviewed
- **WHEN** a candidate exists without a current review snapshot
- **THEN** it is ineligible for confirmation or export and the UI offers `Review answer`

#### Scenario: Student changes reviewed text
- **WHEN** the student edits or selects a different candidate after review
- **THEN** Claros invalidates the review and requires a new snapshot before confirmation

### Requirement: Bound and idempotent confirmation
A review token MUST expire after ten minutes and bind owner, assignment,
question, candidate ID and version, exact-text hash, placement hash, and
assignment version. The first valid confirmation MUST create exactly one new
confirmed-answer revision. An identical network replay MUST return that original
result without another mutation; altered, expired, stale, used-for-different-
content, or cross-owner use MUST fail safely.

#### Scenario: First confirmation succeeds
- **WHEN** the owner submits an unexpired token with the exact bound candidate, placement, and assignment version
- **THEN** Claros stores one confirmed answer, advances the assignment version once, and returns the saved result

#### Scenario: Exact confirmation request is replayed
- **WHEN** the identical successful confirmation request is retried after an uncertain network response
- **THEN** Claros returns the original result and does not create another answer revision

#### Scenario: Confirmation binding is stale
- **WHEN** any bound owner, assignment, question, candidate, text, placement, version, or expiry value no longer matches
- **THEN** Claros rejects confirmation with a recoverable stale-review error and preserves current state

### Requirement: Revision preserves the last confirmed answer
Beginning an edit of a confirmed answer MUST invalidate its prior review token
without deleting the last confirmed revision. Export MUST continue using the
last confirmed revision until the replacement candidate is separately reviewed
and confirmed.

#### Scenario: Student begins a revision
- **WHEN** a confirmed answer is opened for editing
- **THEN** Claros creates an editable candidate while retaining the prior confirmed answer as the exportable version

#### Scenario: Replacement is confirmed
- **WHEN** the revised candidate passes a new exact review and confirmation
- **THEN** it becomes the latest confirmed revision and the assignment version advances once
