# OpenPDF application migration verification

- **Date:** 2026-09-11
- **Branch:** `codex/claros-v2-nerdy`
- **Implementation checkpoint:** `18816eccaf19113d773555174168e42b6386162b`
- **Production activation:** Not performed; `current` remains the explicit Cloud Run template default.

## Runtime and packaging

- Java: Microsoft OpenJDK 21.0.10
- Maven: 3.9.11
- OpenPDF: 3.0.5
- Apache FOP: 2.11
- Apache PDFBox: 3.0.8
- Jackson Databind: 2.20.0
- qpdf: 12.3.2 for local verification
- Font: allowlisted `NotoSans-Regular.ttf`, SHA-256
  `b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5`

The application constructs exactly one selected document executor. Selecting
`openpdf` checks Java, the shaded JAR, qpdf, and the font before startup; it
does not fall back to the current renderer. The production container packages
Java, the shaded worker, font support, and qpdf, but does not select OpenPDF.

## Automated evidence

| Check | Result |
| --- | --- |
| `npm run ci` | Passed: formatting, lint, types, dependencies/licenses, OpenAPI drift, 73 Vitest tests, Storybook build/browser accessibility sweep, production build, and bundle closure |
| Tracked backend replay | 395 passed, 16 OpenPDF skips in the no-qpdf aggregate command; 23 existing dependency deprecation warnings |
| Explicit OpenPDF/container suite | 24 passed with qpdf; covers real endpoint inline/appendix export, Unicode and `ff`/`fi`/`ffi` extraction, immutable source, unconfirmed-draft exclusion, unsupported RTL/glyph rejection, dependency diagnostics, worker crash/timeout, malformed status, contract mutation, wrong coordinates/text, invalid/oversized output, PDFBox raster/validation failure, cleanup, and publication blocking |
| PDF.js release compatibility | Passed against a derivative from the promoted application endpoint; PDF.js is not called by the synchronous publication gate |
| Maven clean package | Passed from the working tree and from a detached clean worktree |
| Ruff | Format check and lint passed |
| OpenSpec | `openspec validate claros-reconstruction --strict` passed |
| Clean worktree | Fresh `npm ci`, `npm run build`, Maven package, Ruff, OpenSpec, and 24 OpenPDF/container checks passed at `18816ec`; worktree stayed clean |

The full frontend gate ran on the available Node 24.14.1 host. The fresh clean
install reported the expected engine warning because the repository requires
Node `>=22.12 <23`; the GitHub release-compatibility job explicitly selects
Node 22.22.0.

## Running-product evidence

The production Vite bundle and FastAPI application ran at
`http://127.0.0.1:8080/app` with `CLAROS_PDF_ENGINE=openpdf`. A headed Chromium
session uploaded a generated three-question worksheet through the actual V2
upload UI. It confirmed the inline answer `The office is efficient; its
official file records café and résumé details.`, confirmed a long answer for an
attached answer page, and left a third typed draft unreviewed and unconfirmed.
The review page reported `2 of 3 answered` and said unanswered questions would
stay blank. The normal V2 download action then completed successfully. The
request trace contained exactly one
`POST /api/v2/assignments/{assignment_id}/exports` with a 201 response.

Local artifacts (ignored by Git) are under `output/playwright/openpdf-migration/`:

| Artifact | SHA-256 |
| --- | --- |
| `05-final-inline-regression-review.png` | `3fca3b85a959178bde06ab802c6252291d1f7657cb2fae5dd17ed975dde72544` |
| `06-final-appendix-review.png` | `aa7fbbc38f714946baeaec773496d6ac1e32fa6b24d7ef870bd118cd9ad29943` |
| `07-final-partial-review.png` | `020daf31e3d3274b9eddea923b1dcb130f98f54a131403c6b1796cd9ddd705bf` |
| `08-final-export-complete.png` | `2d54d8ad72c1a1ac0c3aee47c0afec275dd9f368625fa5adeb33e7f5227eefbb` |
| `openpdf-browser-final-fixture-completed-openpdf.pdf` | `bbae0e4277341b9096b833739d3c03977c8d8b8ead419550631b9628d436009f` |

The 31,626-byte derivative has two pages from a one-page source. qpdf reported
no syntax or stream-encoding errors. Independent pypdf extraction recovered the
accented inline answer exactly, recovered every appendix token in order after
the source page, retained the source-page text in order, and proved the
`UNCONFIRMED-DRAFT-MUST-NOT-EXPORT` canary was absent. The synchronous
application request had already passed the independent PDFBox
text/geometry/source/raster gate before download.

The pinned EmbedPDF preview emitted its previously recorded memory-manager
warnings while replacing source/context documents; the completed route had no
browser console errors. No OpenPDF publication or downloaded-PDF failure was
observed.

## Representative local resource evidence

The promoted endpoint exported three independent synthetic one-page worksheets,
each with one inline answer and an 80-sentence appendix answer:

| Run | OpenPDF | qpdf | PDFBox | Validation total | All subprocesses | Worker internal | Worker peak RSS | PDFBox peak RSS | Temporary peak | Cleanup | Output |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,766 ms | 109 ms | 2,969 ms | 3,078 ms | 4,844 ms | 1,417 ms | 76,787,712 B | 126,808,064 B | 50,142 B | 31 ms | 32,082 B |
| 2 | 1,704 ms | 78 ms | 2,860 ms | 2,938 ms | 4,642 ms | 1,345 ms | 76,890,112 B | 127,852,544 B | 50,140 B | 32 ms | 32,082 B |
| 3 | 1,750 ms | 110 ms | 3,203 ms | 3,313 ms | 5,063 ms | 1,427 ms | 76,713,984 B | 127,950,848 B | 50,139 B | 47 ms | 32,082 B |

These are local development-host observations, not production capacity or SLO
claims. The synchronous validation time is reported separately from rendering.

## Remaining deployment blocker

The local Docker client is present, but its Linux daemon is unavailable:

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine:
The system cannot find the file specified.
```

Therefore no local container-runtime or deployment claim is made. The
dispatchable Ubuntu workflow now builds the packaged worker and runs the real
endpoint plus PDF.js compatibility suite on pull requests, `main`, or manual
dispatch. Production engine activation and deployment remain separately
authorized work.
