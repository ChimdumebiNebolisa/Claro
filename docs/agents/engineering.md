# Claros V2 engineering guidance

## Authority and product boundary

The root V2 execution PRD controls implementation, followed by the product
contract and then the design contract. Older OpenSpec text, tests, code, and git
history are useful only after conflicts are resolved against that order.

V2 supports native-text, sequential short-answer PDFs with at most eight pages
and forty questions. A grounded question may use a validated inline region or
an attached answer page. Reject a document only when its question or required
context cannot be grounded safely; scan-only, encrypted, malformed, oversized,
and unsupported question documents fail with stable reason codes.

## Modules and seams

- `src/domain` owns typed product states, exact-answer integrity, placement
  outcomes, and transition guards. It does not render UI or call vendors.
- `src/domain/assignment-machine.ts` owns the XState graph; feature UI consumes
  snapshots and dispatches typed events.
- `src/adapters` owns the generated API client and browser-facing integrations.
  EmbedPDF and Realtime stay behind narrow document and voice adapters.
- `src/features` owns accessible V2 presentation. It never invents coordinates,
  trusts model output, or commits answers without a server review token.
- `backend` owns FastAPI schemas, assignment services, GCS/local persistence,
  OpenAI adapters, deterministic document analysis, placement, and export.

## Invariants

- Direct answering and guided reasoning are equal entry paths; typed input
  remains complete beneath both.
- Draft, optional rephrase comparison, exact review, and confirmation are
  separate states. A revision invalidates its old confirmation.
- The only voice confirmation phrase is `Use this exact answer`, and it is
  valid only in exact-review state through the same server checks as a button.
- Candidate origin is explicit and server-validated. Suggested wording never
  silently replaces the student's words.
- Physical extraction and deterministic code own coordinates. Models may group
  existing block IDs but cannot create geometry, approve, or write a PDF.
- No safe inline region and inline overflow both route to an attached answer
  page disclosed before confirmation.
- Export is available after one confirmed answer. It uses confirmed answers
  only, leaves unanswered questions blank, preserves exact Unicode text, and
  never overwrites the immutable source object.
- Session and assignment authorization use server-managed signed cookies, not
  browser bearer storage. User and model text is rendered as text, not markup.

## Verification

Test observable behavior through stable interfaces: domain transitions,
OpenAPI contracts, review-token replay/version conflicts, physical-IR and PDF
corpora, exact-text/placement/export invariants, Storybook state stories,
keyboard and screen-reader behavior, Playwright/axe flows, visual screenshots,
and container/deployed persistence smoke. Run the narrowest check after each
slice and every applicable earlier gate before handoff.

## Documentation and change hygiene

Update OpenSpec, README, environment examples, and generated API/schema docs
with durable behavior changes. Keep secrets in local environment files and
never commit private worksheets, raw provider payloads, audio, transcripts, or
unreviewed generated corpus output.

## Visual authority

`CLAROS_V2_DESIGN.md` controls visual and interaction behavior beneath the V2
execution PRD. Untitled UI React is the sole visible V2 component foundation;
EmbedPDF renders authentic source content. The task is first in DOM and visual
order, the marketing hero demonstrates the real product, and legacy styles are
scoped to `/legacy` until removal.
