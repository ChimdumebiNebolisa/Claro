# Claros V2 Product Contract

**Status:** Build contract for the Nerdy AI Hackathon submission  
**Product category:** Accessibility-first, voice-first worksheet completion workspace  
**Primary product sentence:** Claros helps students who find typing difficult answer a worksheet directly or talk through a difficult question, review the exact final wording, and place only the approved answer into a completed PDF.

---

## 1. Product thesis

Many students can formulate an answer more easily than they can type it into a worksheet. The problem is not always comprehension; it is often the physical and operational burden of entering text, moving between a tutor and a PDF, and placing the result into the correct answer area.

Claros closes that loop:

```text
worksheet context
→ direct answer or guided reasoning
→ reviewable final wording
→ explicit student approval
→ reliable PDF completion
```

Claros is not primarily a chatbot and not primarily a PDF editor. It is a **question-by-question learning and completion workspace whose input and output are worksheets**.

---

## 2. Positioning and audience

### 2.1 Primary audience

Students who can express ideas more easily by speaking than by typing, including students affected by:

- dysgraphia;
- motor limitations;
- temporary injury;
- fatigue or pain;
- other barriers to sustained keyboard input.

A diagnosis is not required to use the product.

### 2.2 Age framing

Claros V2 is demonstrated with middle-school and high-school short-answer worksheets, but the product is **not positioned as an all-purpose K–12 platform**.

Current framing:

> Built for students who find typing harder than thinking through the answer.

Nerdy demo framing:

> Starting with secondary-school short-answer worksheets.

Out of scope for V2:

- a child-directed under-13 consumer product;
- elementary reading instruction;
- district administration, teacher dashboards, grading, or classroom rostering.

### 2.3 Core promise

> **The answer is yours. Getting it onto the page can be easier.**

Supporting explanation:

> Say what you know or talk through what you do not. Claros turns your input into a reviewable answer and places only the version you approve onto the worksheet.

Trust statement:

> Nothing is written to the completed PDF until the student approves the exact text.

---

## 3. Two entry paths

Every active question begins with two explicit choices.

```text
[ Say my answer ]
I already know what I want to say.

[ Help me think it through ]
Guide me with one question at a time.
```

Typed input remains available beneath both paths.

### 3.1 Path A — Say my answer

Purpose: remove the typing bottleneck when the student already knows the answer.

Flow:

```text
student speaks or types
→ Claros produces a draft
→ student may keep or improve the wording
→ student reviews exact text
→ student approves
→ Claros writes the answer into the completed PDF
```

Default behavior:

- Preserve the student’s meaning and wording.
- Normalize punctuation, capitalization, and obvious speech disfluencies.
- Do not introduce a new factual claim.
- Do not silently replace the draft with polished model language.

Available actions:

- **Use my words** — keep the normalized transcription.
- **Make it clearer** — request a visibly labeled suggested rephrasing.
- **Edit** — manually change the draft.
- **Use this answer** — explicitly approve the exact visible text.

### 3.2 Path B — Help me think it through

Purpose: provide contextual tutoring without turning the product into an automatic answer generator.

Flow:

```text
student states uncertainty
→ Claros asks one focused guiding question
→ student develops the idea
→ Claros asks the student to state a final answer
→ final answer becomes a reviewable candidate
→ student approves
→ Claros writes the answer into the completed PDF
```

Tutor behavior:

- Start from the active worksheet question and visible source context.
- Prefer one targeted question at a time.
- Avoid long lectures unless requested.
- Do not silently convert the conversation transcript into a final answer.
- Ask the student to state the final answer in their own words.
- When offering suggested wording, label it clearly as a Claros suggestion.

### 3.3 The two paths converge

Both paths end at the same mandatory review state:

```text
FINAL ANSWER
[exact answer text]

This exact text will be added to Question N.

[ Change answer ]   [ Use this answer ]
```

No path bypasses exact review and approval.

---

## 4. Answer provenance and student control

### 4.1 Claros may

- transcribe speech;
- normalize punctuation and obvious speech artifacts;
- ask guiding questions;
- suggest clearer wording when requested;
- show a suggestion beside the student’s original wording;
- place the selected answer into the completed PDF;
- route long answers to an attached answer page.

### 4.2 Claros may not

- silently create a final answer from the worksheet alone;
- treat tutoring conversation as answer approval;
- hide that wording was suggested or changed by the model;
- infer approval from casual phrases such as “yeah” or “okay” during tutoring;
- write an answer before explicit confirmation;
- claim that model-rephrased text was verbatim student language;
- invent PDF coordinates or unsupported document structure.

### 4.3 Candidate origin

Every answer candidate carries one origin value:

```text
student_verbatim
student_normalized
claros_rephrase
student_after_guidance
student_edited
```

The user interface exposes the meaningful distinction:

- **Your words**
- **Suggested wording**

Internal provenance is retained for validation and testing, not displayed as technical telemetry.

### 4.4 Rephrasing contract

When the student selects **Make it clearer**, the interface shows both versions:

```text
YOUR WORDS
Plants need sunlight because it helps them make their food.

SUGGESTED WORDING
Plants use sunlight to make food through photosynthesis.

[ Keep my wording ]   [ Use suggestion ]
```

The suggestion does not become final until selected and subsequently approved.

---

## 5. Voice interaction contract

### 5.1 Voice-first, never voice-only

The complete workflow must remain usable through:

- speech;
- keyboard;
- pointer or touch;
- accessible switch/keyboard navigation where supported by the browser.

### 5.2 Explicit voice confirmation

Voice may be used to approve an answer only after:

1. the exact final text is visible;
2. Claros has offered to read it aloud;
3. the interface is in the dedicated confirmation state; and
4. the student gives an exact confirmation command such as **“Use this exact answer.”**

Casual agreement during conversation does not count.

### 5.3 Required voice states

The interface exposes text labels for:

```text
Ready
Listening
Thinking
Speaking
Interrupted
Connection lost
Microphone unavailable
```

A waveform or color change may supplement these labels but may not replace them.

### 5.4 Required voice controls

- Start speaking
- Stop listening
- Interrupt Claros
- Mute/unmute spoken output
- View live captions
- Continue by typing

Voice disconnection must preserve the current draft and conversation state.

---

## 6. Worksheet and PDF contract

### 6.1 Supported V2 document class

V2 supports native-text, sequential short-answer PDF worksheets in which question text can be grounded to source content.

Initial limits:

- up to 8 pages;
- up to 40 questions;
- machine-readable text;
- short-answer prompts;
- no required freehand drawing;
- no claim of arbitrary PDF compatibility.

Scanned/image-only PDFs are rejected with a clear explanation in V2. OCR is a later capability.

### 6.2 Source immutability

The uploaded source PDF is never overwritten.

Claros creates a derivative completed file from:

```text
immutable original PDF
+ exact confirmed answers
+ validated placement decisions
```

### 6.3 Physical and semantic separation

The document engine has three responsibilities:

1. **Physical extraction** — deterministic text, page, line, rectangle, form-field, and coordinate evidence.
2. **Semantic mapping** — an OpenAI model groups existing source blocks into questions and context using block identifiers.
3. **Geometry resolution** — deterministic code decides whether and where an answer can be placed.

The model may identify source block IDs. It may not generate authoritative coordinates.

### 6.4 Question fidelity

- Question wording is copied exactly from source evidence.
- Claros does not paraphrase questions in the completed document.
- Question order follows the original document.
- Questions that cannot be grounded confidently cause a controlled rejection rather than an invented mapping.

### 6.5 Placement outcomes

Every confirmed answer receives one of three outcomes:

#### Inline placement

Used when the original worksheet contains a validated answer region with adequate readable space.

#### Attached answer page

Used when the question is understood but the original page has no safe region or the approved answer cannot fit at a readable size.

The attached page includes:

- exact original question text;
- original source page number;
- exact approved answer;
- a stable question identifier.

#### Rejection

Used when the question or relevant source context cannot be grounded safely.

Claros never shrinks text indefinitely, overlaps surrounding content, or guesses where an answer belongs.

### 6.6 Export behavior

- Export is available after at least one answer has been confirmed.
- Unanswered questions remain blank.
- The student may review and revise confirmed answers before export.
- Revising an answer invalidates the old confirmation and requires approval again.
- Export preserves ordinary Unicode text and punctuation.
- The final PDF must open in current Chrome and Adobe Acrobat Reader.

### 6.7 Default artifact

The default output is one completed PDF containing:

1. original worksheet pages with safe answers placed inline; and
2. attached answer pages for answers that could not safely fit inline.

A fully reconstructed worksheet is not the default because it can detach questions from instructions, diagrams, equations, and surrounding context.

---

## 7. Student interface contract

### 7.1 State sequence

```text
upload
→ document check
→ worksheet ready
→ question focus
→ choose answer path
→ direct answer or guided reasoning
→ exact review
→ answer added
→ next question / all-answer review
→ export
```

### 7.2 Question-first workspace

During learning, the active question is the primary unit. The interface shows:

- exact question text;
- a crop or compact view of relevant source context;
- a link/button to view the full original page;
- the two entry paths;
- the current draft or tutoring state.

A full PDF and dense inspector may appear in review/debug contexts, but a resizable PDF/editor split is not required for normal student use.

### 7.3 Initial question screen

Required actions:

```text
Say my answer
Help me think it through
Type instead
View worksheet
```

The two paths must be understandable without onboarding or tooltips.

### 7.4 Exact-review screen

The final answer is visually separated from:

- tutoring transcript;
- rough speech transcript;
- source worksheet text;
- model explanation.

Required actions:

```text
Hear it
Edit
Use my words / Use suggestion, when applicable
Use this answer
```

### 7.5 Placement feedback

Student-facing copy:

- **Your answer fits on the worksheet.**
- **This answer will appear on an attached answer page.**
- **Claros could not safely match this question.**

Do not expose raw X/Y coordinates, font telemetry, character metrics, vector terminology, or internal plan tokens.

### 7.6 One dominant action per state

Examples:

- Choose a path
- Stop speaking
- Use this answer
- Continue to Question N
- Download completed PDF

Secondary actions remain visible but visually subordinate.

---

## 8. Accessibility requirements

### 8.1 Interaction

- Complete keyboard path.
- Visible focus rings.
- No drag-only or resize-only requirement.
- Minimum 44×44 CSS-pixel primary targets.
- No action represented only by color.
- No forced time limit for answering.

### 8.2 Legibility

- Application body and controls: 15–16px minimum target size.
- Question text: 20px or larger on desktop.
- Supporting status text: 13px minimum.
- Strong text/background contrast.
- Sans-serif typography throughout the application.

### 8.3 Audio and motion

- Live captions for both student and Claros speech.
- Spoken output may be muted while text remains available.
- Respect `prefers-reduced-motion`.
- Answer-placement animation must degrade to an immediate state change.

### 8.4 Error recovery

- Microphone failure never blocks typed completion.
- Realtime failure preserves the current answer draft.
- Export failure does not erase confirmed answers.
- Unsupported PDF errors state what is unsupported and offer the sample worksheet.

---

## 9. Marketing contract

### 9.1 Approved framing

- Accessibility-first worksheet workspace
- Voice-first, not voice-only
- Direct answering or guided reasoning
- Exact student approval
- Original PDF preserved
- Completed PDF returned

### 9.2 Prohibited or unsubstantiated claims

Do not publish claims such as:

- “used across 1,200+ classrooms”;
- FERPA/COPPA certification;
- teacher oversight dashboards;
- LMS integrations;
- “zero layout drift”;
- guaranteed compatibility with all worksheets;
- “every character was written by the student” when Claros can rephrase;
- free pricing, enterprise deployment, or incorporation claims unless true.

### 9.3 Recommended FAQ answer

**Does Claros answer the worksheet for me?**

> Claros can transcribe what you say, help you think through a question, and suggest clearer wording. You choose the final answer and review the exact text before Claros writes it onto the worksheet.

---

## 10. Visual design contract

### 10.1 Brand qualities

```text
calm
capable
accessible
precise
student-controlled
```

Not:

```text
enterprise-autonomous
childish
clinical PDF debugger
chatbot dashboard
```

### 10.2 Marketing surface

- editorial serif for major headings only;
- sans-serif for body text, navigation, and controls;
- white and atmospheric blue surfaces;
- cobalt primary action;
- generous whitespace;
- real workflow transformation above the fold;
- one dark trust section;
- no fabricated telemetry or social proof.

### 10.3 Application surface

- sans-serif throughout;
- solid, high-contrast surfaces;
- large controls;
- 8–12px control radius and 12–16px card radius;
- limited status chips;
- no glass effect behind critical text;
- no tiny uppercase operational labels;
- no mascots, streaks, points, or confetti.

### 10.4 Meaningful motion

Animation is limited to:

1. voice-state transitions;
2. answer candidate moving into its worksheet destination;
3. question-to-question progression.

---

## 11. Technical boundary

```text
Claros
│
├── Cloud Run                         keep
├── Google Cloud Storage              keep
│
├── Document engine                   rebuild
│   ├── PDF preflight/normalization
│   ├── deterministic physical IR
│   ├── OpenAI semantic block mapping
│   ├── deterministic region resolver
│   └── derivative PDF assembly
│       ├── safe answers inline
│       └── unsafe answers on attached pages
│
├── React application                 rebuild the flow
│   ├── React + Vite
│   ├── Tailwind/CSS tokens + Radix
│   ├── XState for user-visible workflow
│   ├── TanStack Query for server state
│   ├── Motion for bounded transitions
│   ├── Storybook + MSW for states
│   └── React-PDF for source rendering
│
├── OpenAI Realtime
│   ├── browser WebRTC
│   ├── short-lived credential from backend
│   └── direct answering + contextual tutoring
│
└── OpenAI Responses
    ├── semantic source-block grouping
    ├── structured outputs
    └── no authoritative geometry
```

Suggested PDF stack for the permissive-license V2 path:

```text
pikepdf
pdfplumber
reportlab
pypdf
```

---

## 12. V2 state machine

```text
idle
└── uploading
    ├── rejected
    └── analyzing
        ├── rejected
        └── ready
            └── question.focus
                ├── path.select
                │   ├── direct.ready
                │   │   ├── direct.listening
                │   │   └── direct.drafting
                │   └── guided.ready
                │       ├── guided.listening
                │       ├── guided.thinking
                │       ├── guided.speaking
                │       └── guided.finalizing
                ├── candidate.review
                │   ├── candidate.compare
                │   ├── candidate.edit
                │   └── candidate.confirming
                ├── placement.inline
                ├── placement.appendix
                └── answer.saved
                    ├── question.next
                    └── worksheet.review
                        ├── answer.revise
                        └── export.ready
                            ├── exporting
                            ├── export.failed
                            └── export.complete
```

---

## 13. Demo scope and acceptance criteria

### 13.1 Required demo corpus

- one polished high-school biology worksheet;
- one middle-school science worksheet;
- one non-science short-answer worksheet;
- generated variants covering line boxes, blank regions, multi-page order, long answers, Unicode, and appendix routing;
- one controlled scanned-PDF rejection.

### 13.2 Required end-to-end demonstrations

1. Direct voice answer.
2. Guided reasoning answer.
3. Optional visible rephrasing comparison.
4. Exact answer approval.
5. Inline answer placement.
6. Attached answer-page fallback.
7. Revision invalidating prior confirmation.
8. Completed PDF export.
9. Microphone failure with typed continuation.

### 13.3 Pass/fail invariants

- Exported text exactly matches the approved answer.
- No model-generated coordinate is treated as physical truth.
- No answer overlaps source content.
- No answer is reduced below the configured readable-size floor.
- Overflow moves to the attached answer page.
- Original PDF bytes remain unchanged in storage.
- Question wording is copied from source evidence.
- Keyboard-only completion works.
- Realtime failure does not lose the draft.
- No unsupported product claim appears in the public mockup.

---

## 14. Build order

1. Freeze this contract and the state machine.
2. Build all interface states in Storybook with fixtures and no live model calls.
3. Implement the PDF engine against the gold corpus.
4. Connect upload, assignment, confirmation, placement, revision, and export APIs.
5. Add OpenAI Realtime after the deterministic workflow is complete.
6. Record the final demo only after both entry paths and both placement outcomes pass end-to-end tests.

---

## 15. Final decision rule

A feature belongs in Claros V2 only when it strengthens this loop:

```text
understand the exact worksheet question
→ let the student answer or learn
→ preserve the student’s final choice
→ return one usable completed PDF
```

Anything else is deferred.
