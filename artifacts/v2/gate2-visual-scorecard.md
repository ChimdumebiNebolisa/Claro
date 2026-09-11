# Gate 2 visual quality scorecard

- **Content checkpoint:** `0723303ef718bb28594d519da31ec0a55226fa45`
- **Evidence manifest:** `artifacts/v2/screenshots/manifest.json`
- **Matrix:** 36 captures: the 33 required state/viewport combinations plus
  desktop and mobile marketing and the mobile full-screen worksheet dialog
- **Capture boundary:** local Vite and fixture API only; zero external requests
- **Review date:** 2026-09-04

## Authority rubric

| Category | Available | Lead | Read-only reviewer | Evidence conclusion |
|---|---:|---:|---:|---|
| Product hierarchy | 20 | 19 | 19 | Active question and one primary action dominate; the supporting source remains secondary. |
| Component consistency | 15 | 14 | 14 | Untitled/React Aria controls, radii, icons, focus, and semantic tokens remain consistent across states. |
| Legibility and accessibility | 20 | 19 | 19 | Question type, supporting-text floor, focus order, live regions, zoom, and axe checks pass. |
| PDF authenticity | 15 | 15 | 15 | Source crops and the full dialog use EmbedPDF; confirmed states show the authentic derivative PDF. |
| State clarity | 15 | 14 | 14 | Voice, provenance, comparison, exact review, destination, failure, and export states remain distinct. |
| Responsive behavior | 10 | 9 | 9 | Task-first DOM order, mobile dialog, tablet stacking, zoom reflow, and overflow checks pass. |
| Restraint and credibility | 5 | 5 | 5 | No fake metrics, unsupported integrations, fabricated worksheet, AI glow, or decorative telemetry. |
| **Total** | **100** | **95** | **95** | **Pass** |

Every category is at least 90 percent of its available points. The Gate 2
threshold is 90 overall with no category below 80 percent.

## Review disposition

- Zero critical accessibility defects were found in the complete Storybook
  sweep or principal-route axe replay.
- Zero anti-reference violations were found.
- The five supporting labels initially below the 13px authority floor were
  corrected and re-reviewed.
- Question 2 and Question 3 use question-bound source crops and accessible
  names. Confirmed states use a completed-copy preview while explicitly
  stating that the source page is preserved.
- The mobile worksheet dialog does not announce readiness until an actual PDF
  page image is decoded and rendered.
- Fake Realtime behavior is Gate 2 evidence only. Live WebRTC, ephemeral
  credentials, and provider recovery remain Gate 5 work.
- Fixture PDF placement is Gate 2 evidence only. Dynamic server-owned geometry,
  source revalidation, and deterministic export remain Gate 3 work.

## Verification

`node scripts/verify-gate2-screenshots.mjs` verified all 36 exact files,
dimensions, SHA-256 values, the content checkpoint, and zero external requests.
The final serialized Playwright replay passed 22 of 22 tests, including the
required desktop, tablet, mobile, keyboard, focus, reduced-motion, zoom,
revision, failure-recovery, partial-export, and voice-authority paths.
