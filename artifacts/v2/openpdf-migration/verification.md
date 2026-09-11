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
| Explicit OpenPDF/container suite | 24 passed with qpdf; covers real endpoint inline/appendix export, Unicode and `ff`/`fi`/`ffi` extraction, immutable source, unconfirmed-draft exclusion, dependency diagnostics, worker crash/timeout, malformed status, contract mutation, wrong coordinates/text, invalid/oversized output, PDFBox raster/validation failure, cleanup, and publication blocking |
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
session uploaded `backend/tests/corpus/01-biology-polished.pdf`, confirmed one
inline answer and one long attached-page answer through exact review, exported
through the normal V2 action, and downloaded the result. The request trace
contained exactly one `POST /api/v2/assignments/{assignment_id}/exports` with a
201 response.

Local artifacts (ignored by Git) are under `output/playwright/openpdf-migration/`:

| Artifact | SHA-256 |
| --- | --- |
| `01-inline-exact-review.png` | `968d2a9e7beadd346ec93af924095989cea9d7c696242d426c2f5277be16f520` |
| `02-appendix-exact-review.png` | `5e3751875c15c3e183335ea0bb8d12e83e7dcf993afd526be2cc6fd174f03597` |
| `03-worksheet-review.png` | `88b29ba64fc681f96df2d80b05450ff9d451018fe08c63dc5809729e5dd371e0` |
| `04-export-complete.png` | `ef14720d0f49186ccfd84c75afc871db4ed7a285b9fb1d1b8a11f8395df06728` |
| `01-biology-polished-completed-openpdf.pdf` | `a5170c9e260ebe0f7cc9663397ce650883c1c2c2cf9f83c25b5362f877e1c86b` |

The 32,138-byte derivative has two pages from a one-page source. qpdf reported
no syntax or stream-encoding errors. Independent pypdf extraction recovered the
inline answer exactly, recovered every appendix token in order, and retained
the source-page text in order. The synchronous application request had already
passed the independent PDFBox text/geometry/source/raster gate before download.

The pinned EmbedPDF preview emitted its previously recorded memory-manager
warnings while replacing source/context documents; the completed route had no
browser console errors. No OpenPDF publication or downloaded-PDF failure was
observed.

## Representative local resource evidence

The promoted endpoint exported a synthetic one-page worksheet with one inline
answer and an 80-sentence appendix answer:

| Measure | Result |
| --- | ---: |
| OpenPDF process | 1,922 ms |
| qpdf | 94 ms |
| PDFBox | 3,281 ms |
| Validation total | 3,375 ms |
| All subprocesses | 5,297 ms |
| Worker internal render | 1,548 ms |
| Worker peak RSS | 76,308,480 bytes |
| PDFBox peak RSS | 128,712,704 bytes |
| Temporary job peak | 50,140 bytes |
| Cleanup | 31 ms |
| Output | 32,082 bytes |

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
