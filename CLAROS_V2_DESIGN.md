# Claros V2 Design System

**Status:** Visual and interaction authority for the V2 mockup and implementation  
**Date:** 2026-09-04

---

## 1. Design thesis

Claros combines an editorial, calm marketing surface with a direct, highly legible student workspace.

The design should communicate four ideas without relying on copy:

1. **The student is in control.**
2. **Speaking is easier than typing, but never mandatory.**
3. **The worksheet remains the source of truth.**
4. **Claros turns an approved answer into a completed document.**

The interface must not resemble an enterprise monitoring console, a generic chatbot, a PDF-debugging tool, or a children’s game.

### Brand character

- Calm
- Capable
- Accessible
- Precise
- Student-controlled
- Mature enough for high-school and college use

### Visual formula

```text
Round-inspired editorial atmosphere
+ high-contrast accessible application surfaces
+ concrete worksheet transformation
- enterprise telemetry
- AI-glow theater
- fake institutional claims
```

---

## 2. Product hierarchy

The product is organized around the student’s current question, not a permanent chatbot and not a permanent full-page PDF editor.

### Primary hierarchy during question work

1. Question progress
2. Exact question text
3. Two entry paths or the currently selected path
4. Current answer or tutoring turn
5. Exact-answer review
6. Source context

### Source worksheet behavior

- Desktop: visible as a supporting pane beside the task workspace
- Tablet: stacked after the task workspace
- Mobile: task workspace appears first; source context is available below or through **View full worksheet**
- No required panel resizing
- No drag-to-place interaction
- No raw coordinates, font metrics, parser confidence, or bounding-box telemetry in the normal interface

---

## 3. Core screen: question choice

Every unanswered question starts with two equally weighted choices.

### Say my answer

**Description:** Already know it? Speak or type the answer directly. Claros handles transcription and placement.

**Visual treatment:**

- Microphone/speech icon
- White card
- Blue-tinted icon container
- Strong title
- One-sentence explanation
- Text action: **Start answering →**

### Help me think it through

**Description:** Not sure how to explain it? Work through the idea with Claros before choosing final wording.

**Visual treatment:**

- Guidance/spark icon
- Same size and visual weight as direct-answer card
- Text action: **Start a guided conversation →**

Neither card is labeled recommended. The product must not assume that typing difficulty implies lack of understanding.

---

## 4. Core screen: direct-answer path

### Required components

- Pinned exact question text
- Explicit voice state: Ready, Listening, or Captured
- Live/finished transcript labeled **Your words**
- Editable typed field
- Secondary actions:
  - **Edit words**
  - **Make it clearer**
- Primary action:
  - **Review answer →**

### Rephrasing comparison

When **Make it clearer** is selected, show two selectable cards:

```text
YOUR WORDS                     SUGGESTED WORDING
[student-derived version]      [AI rephrasing]
```

The selected card has a clear border and background change. The final-answer preview updates immediately.

---

## 5. Core screen: guided-reasoning path

### Required components

- Pinned exact question text
- Student and Claros turns with distinct but restrained surfaces
- One focused Claros prompt at a time
- Live captions and interruption controls in the functional product
- **I am ready to answer →** action
- Exact-answer review after the student states a final response

### Conversation styling

- Student: dark ink surface, white text
- Claros: pale-blue surface, dark text
- Do not use avatars, animated mascots, or decorative chat wallpaper
- Do not let the transcript extend indefinitely; collapse prior turns when the active task requires more space

---

## 6. Exact-answer review

This is the most important control state in the product.

### Required hierarchy

1. Eyebrow: **Exact answer review**
2. Instruction: **Read every word before it reaches the worksheet.**
3. Provenance label:
   - **Your words**
   - **Suggested wording**
4. Exact final-answer text
5. Destination status:
   - **This answer fits on the original worksheet**
   - **This answer will use an attached answer page**
6. Actions:
   - **Change answer**
   - **Use this exact answer →**

### Forbidden copy

- Commit
- Inject
- Stamp
- Author lock
- Target space
- Placement token
- Semantic validation
- Immutable vector layer

These may exist internally but must not appear in the student experience.

---

## 7. Answer-added transition

The preferred transition visually connects the approved answer card to the answer area in the worksheet.

### Motion sequence

1. Primary approval button enters a brief loading state.
2. The answer card contracts or fades toward the document pane.
3. The answer region highlights.
4. The exact text appears in the destination.
5. Status appears: **Answer added to the worksheet.**

### Reduced-motion behavior

Immediately update both states and announce the result through an accessible status region. No essential meaning depends on animation.

---

## 8. Marketing-page structure

### Navigation

```text
Claros   Two ways to answer   Student control   Prototype   [Try the mockup]
```

Do not show sign-in, pricing, integrations, educator portals, or compliance pages until they exist.

### Hero

**Headline**

> The answer is yours.  
> *Getting it onto the page* can be easier.

**Supporting copy**

> Say what you know or talk through what you do not. Claros turns your words into a reviewable answer and puts only the version you approve onto the worksheet.

**Trust line**

> Nothing is written until you approve the exact text.

The hero should contain one concrete application mockup, not abstract AI imagery.

### Two-path section

Explain the direct and guided paths side by side and show that they converge on exact review.

### Dark trust section

Use one high-contrast section for four guarantees:

- Choose your route
- See every wording change
- Approve the exact text
- Keep the source pages

### Final CTA

> Put your next answer on the page.  
> *Speaking, typing, or both.*

---

## 9. Color system

```css
--ink: #111827;
--muted: #5d6677;
--quiet: #8b94a5;
--line: #dfe5ef;
--line-strong: #cbd5e1;
--paper: #ffffff;
--soft: #f7f9fc;
--blue: #075ee8;
--blue-dark: #064bbb;
--blue-soft: #eef5ff;
--blue-mist: #dcecff;
--green: #16835d;
--green-soft: #ecf9f3;
--amber: #ad6411;
--amber-soft: #fff8e8;
--night: #090b10;
--night-card: #121722;
```

### Usage rules

- Blue: primary action, focus, selected path, active question
- Green: completed and safely placed states only
- Amber: attention or answer-page fallback, not general decoration
- Red: actual errors only
- Pale-blue gradients: marketing atmosphere, not behind dense application text
- Dark surfaces: one trust section and student chat bubbles; not the entire product

---

## 10. Typography

### Marketing

Use one editorial serif for hero and section headlines. The mockup uses a system editorial stack so the prototype remains self-contained; production may use Instrument Serif if loaded and licensed appropriately.

```css
font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
```

### Application

Use Inter or the existing product sans-serif throughout.

```css
font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
```

### Minimum sizes

- Application body: 15–16 px
- Question text: 28–38 px desktop, 26–32 px mobile
- Button text: 14–16 px
- Status/supporting text: 12–14 px
- Avoid 10 px interface text except nonessential marketing annotations

---

## 11. Shape, spacing, and elevation

### Radius

- Buttons: 10–12 px
- Small cards/fields: 10–12 px
- Workflow cards: 14–18 px
- Major app shell: 20–24 px
- Do not use full pills for every control

### Spacing

Use an 8 px base rhythm with larger 12/20/28/40 px working increments. Question screens need generous space around the prompt and answer controls.

### Elevation

- Application panels: subtle border before shadow
- Main product mockup: one broad ambient shadow
- Active review card: blue-tinted border and restrained shadow
- No glow on ordinary controls

---

## 12. Accessibility requirements

- No interaction requires dragging or resizing
- Complete keyboard flow
- Minimum 44 px primary interactive target height
- Clear focus-visible states
- Live captions for voice interaction
- Voice state is written explicitly, not shown only by a waveform
- No color-only status
- High-contrast body text on solid surfaces
- Typed fallback available at every point
- Reduced-motion behavior implemented
- Task content appears before full worksheet context on narrow screens

---

## 13. Component inventory

### Foundation

- `AppShell`
- `TopBar`
- `ProgressLabel`
- `SourceContextPane`
- `QuestionHeader`

### Entry paths

- `EntryPathChoice`
- `DirectAnswerCard`
- `GuidedReasoningCard`
- `VoiceStateControl`
- `LiveTranscript`
- `ConversationTurn`

### Answer control

- `WordingComparison`
- `AnswerReviewCard`
- `DestinationStatus`
- `ApprovalButton`
- `AnswerAddedState`

### Document

- `WorksheetPreview`
- `ActiveQuestionRegion`
- `CommittedAnswerOverlay`
- `AnswerPagePreview`

### System states

- `DocumentCheckState`
- `UnsupportedDocumentState`
- `VoiceUnavailableState`
- `ExportProgressState`
- `ExportCompleteState`

---

## 14. Implementation guidance

Keep the current React, Vite, TypeScript, Tailwind/Radix, XState, React-PDF, Storybook, and Playwright foundation. Rebuild the information architecture and component states rather than replacing the framework.

Recommended additions:

- Motion for limited answer-placement and state transitions
- TanStack Query for server state
- MSW for deterministic Storybook and test states
- OpenAI Agents SDK for Realtime voice integration

The mockup is a product-direction artifact, not production code. Production implementation should translate its layout into reusable React components and validate every state in Storybook before connecting live Realtime or PDF services.
