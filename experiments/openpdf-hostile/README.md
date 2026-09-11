# OpenPDF hostile-PDF investigation

This directory is an isolated decision harness for evaluating LibrePDF/OpenPDF as a possible Claros PDF engine. It does not import, call, or modify the production export endpoint. Every fixture and derivative is written below this experiment's ignored `target/` directory.

## Decision boundary

The harness asks whether OpenPDF can add exact approved text at an already-authorized physical placement while preserving an arbitrary source PDF. It does not decide whether a placement is safe. Claros's deterministic server placement authority remains upstream of this experiment.

The implementation preserves these Claros contracts:

- Source PDFs are treated as immutable bytes. The SHA-256 is recorded before and after derivative creation.
- Source pages are stamped through `PdfReader`/`PdfStamper`; they are never reconstructed as new pages.
- Only explicit synthetic overlay strings enter a derivative. No draft, transcript, or model output exists in the harness.
- Placement is crop-relative, top-left physical points and is transformed explicitly. OpenPDF's implicit rotated-content transform is disabled.
- Unsupported glyphs fail before a derivative is published.
- Continuation pages retain all source pages and contain the worksheet title, source page number, stable question ID, exact source question, exact approved answer, and visible page numbers.
- Independent validation must reopen the derivative and verify page structure, preserved source semantics, exact overlay extraction, physical coordinates, and source immutability.

The contract review covered:

- `AGENTS.md` and `docs/agents/engineering.md`.
- `openspec/changes/claros-reconstruction/specs/safe-export/spec.md`.
- `openspec/changes/claros-reconstruction/specs/deterministic-placement/spec.md`.
- `openspec/changes/claros-reconstruction/specs/answer-integrity/spec.md`.
- The current Python `backend/document/renderer.py` and `backend/document/exporter.py` implementation and `backend/tests/document/` tests.
- `origin/main` at `5fb217715e4b3278f21a882b2652d928f2cca628`, including its committed-answer/placement contracts, minimal `server/fixture.mjs` PDF export, and PDF/placement tests. The checkout was not switched because the working tree contains unrelated user changes; inspection used read-only Git object commands.

The active reconstruction specifications are stricter than the older `origin/main` implementation and are the acceptance bar used by this harness.

## Corpus

All PDFs are project-authored synthetic documents produced deterministically with Apache PDFBox. No third-party worksheets are downloaded. Font programs used by fixtures and overlays are checksum-pinned Noto fonts under the SIL Open Font License; see `THIRD_PARTY_NOTICES.md`.

| Fixture | Hostile characteristic |
|---|---|
| `normal-letter` | US Letter and five corner/center placements, including PDF-sensitive characters |
| `a4` | A4 page |
| `mixed-page-sizes` | Letter, A4, and legal pages |
| `rotated-90` | 90-degree page rotation |
| `rotated-180` | 180-degree page rotation |
| `rotated-270` | 270-degree page rotation |
| `cropbox-offset` | CropBox offset from MediaBox and boundary placements |
| `trim-bleed-boxes` | Distinct TrimBox and BleedBox |
| `mixed-rotations` | Multiple pages with different rotations |
| `annotations` | Existing text annotation |
| `acroform` | Existing AcroForm field and value |
| `embedded-font` | Existing embedded Noto Sans program |
| `unicode-text` | Curly punctuation and non-ASCII names |
| `accented-latin` | `é ñ ü à ç å` |
| `mathematical-symbols` | Greek and mathematical symbols |
| `cjk` | Simplified Chinese source and overlay |
| `arabic-rtl` | Arabic RTL capability probe |
| `hebrew-rtl` | Hebrew RTL capability probe |
| `long-multiline-answer` | Exact answer spanning three attached pages |
| `existing-images` | Existing raster image |
| `vector-graphics` | Existing paths and strokes |
| `transparency` | Existing alpha-blended graphics |
| `object-stream-heavy` | PDF 1.6 object streams across 24 pages |
| `office-style` | Synthetic table/report equivalent to common office output |
| `scanned-image-only` | Full-page raster scan with no source text |
| `large-multipage` | 60 source pages |
| `encrypted` | AES-128 encrypted source with known user and owner passwords |
| `malformed-readable` | Deterministically damaged `startxref` that both qpdf and OpenPDF rebuild |
| `outlines` | Existing nested bookmarks/outlines |
| `links` | Existing URI link annotation |
| `metadata` | Document information dictionary plus XMP packet |
| `user-unit-2` | Non-default `/UserUnit 2` capability probe |
| `emoji` | Monochrome emoji font and supplementary-plane character probe |

`CorpusPlanTest` prevents accidental removal of a required class.

## Physical coordinate model

A placement is `(page, xPt, baselineFromTopPt)` relative to the visible CropBox after page rotation. Values are physical points, so `/UserUnit` is applied explicitly. For CropBox `(llx, lly, width, height)`, physical coordinates are divided by `UserUnit` and mapped as follows:

| `/Rotate` | PDF user-space anchor |
|---|---|
| 0 | `(llx + x, lly + height - y)` |
| 90 | `(llx + y, lly + x)` |
| 180 | `(llx + width - x, lly + y)` |
| 270 | `(llx + width - y, lly + height - x)` |

The matching text matrices keep text upright in physical display space. Unit tests assert forward/inverse round trips for all four rotations and non-default CropBox/UserUnit values. Each overlay also draws a small magenta physical-coordinate marker. PDFBox raster validation locates that marker within 1.75 physical points of the requested point and rejects changes outside a conservative overlay mask. Raster scale is derived from the rendered page dimensions, avoiding assumptions about how a renderer exposes `/UserUnit`.

## Stamping strategy

For a source whose cross-reference table OpenPDF can read without rebuilding, the harness uses incremental `PdfStamper` mode. This keeps original bytes and objects in the derivative and disables automatic document-info/XMP updates. This is necessary: `PdfStamperMetadataModeTest` proves that the default full-rewrite constructor changes the Producer value on close.

OpenPDF rejects incremental stamping when `PdfReader.isRebuilt()` is true. The deterministic malformed fixture therefore uses a visible full-rewrite fallback and explicitly restores the source information dictionary. That fallback is reported per case and is not silently treated as equivalent to incremental preservation.

Encrypted sources are opened with the owner password. Incremental stamping retains the source encryption dictionary and permissions; the derivative is independently reopened with the user password and inspected with qpdf.

For non-RTL text the harness explicitly disables OpenPDF's FOP-backed glyph substitution. The default substitution path collapses Noto Sans `ff`, `fi`, and `ffi` sequences to one glyph but writes only the first source character into the glyph's ToUnicode mapping. The isolated `office` investigation and regression test prove the defect and the configuration; RTL probes retain substitution because shaping requires it.

## Validation layers

The harness uses engines independent of OpenPDF so a single implementation cannot certify itself:

1. OpenPDF reopens every derivative.
2. PDFBox compares source-page MediaBox, CropBox, TrimBox, BleedBox, ArtBox, rotation, UserUnit, annotations, form fields, outlines, information metadata, XMP hash, encryption permissions, image pixels, and embedded font programs.
3. PDFBox extracts source and overlay text, renders every source page at 96 DPI, and checks that no pixels changed outside approved overlay masks.
4. qpdf `--check` validates source and derivative syntax, streams, encryption, and recovery warnings.
5. PDF.js in headless Chromium reopens and renders every derivative page and independently probes exact overlay extraction.
6. Continuation validation checks page count, stable question ID, exact question fragments, exact answer fragments in order, and visible page numbering.

`PASS` means all machine-verifiable assertions in that column passed. `PARTIAL` means the tested behavior rendered/reopened but a required property could not be proved automatically. `FAIL` is an observed mismatch or safe rejection. `NOT_APPLICABLE` means the fixture does not exercise that capability.

Generated evidence is in:

- `target/evidence/fixture-manifest.json` — source checksums and sizes.
- `target/evidence/results.json` — complete per-case structured evidence.
- `target/evidence/results-table.md` — generated decision table.
- `target/fixtures/` and `target/derivatives/` — immutable-run inputs and separate OpenPDF outputs.

## Running

Requirements are Java 21+, Maven, Node, and the repository's installed `pdfjs-dist` and Playwright Chromium. The PowerShell entrypoint downloads the official qpdf 12.3.2 Windows archive only if needed and verifies its pinned SHA-256 before extraction. Font downloads are likewise commit- and checksum-pinned.

From this directory:

```powershell
.\scripts\run.ps1
```

Individual phases:

```powershell
mvn test
mvn exec:java "-Dexec.args=run"
node scripts/validate-pdfjs.mjs target/evidence/pdfjs-cases.json target/evidence/pdfjs-results.json
mvn exec:java "-Dexec.args=report"
```

The focused extraction investigation is reproducible separately and does not add corpus cases:

```powershell
.\scripts\investigate-office.ps1
```

It produces PDFBox structure/extraction JSON, PDF.js extraction JSON, qpdf checks, QDF-expanded source/derivative files, and the A/B/C/D comparison under `target/office-investigation/`. The minimum deployment isolation for untrusted inputs is specified in `security-boundary.md`; it is design-only and is not implemented by this experiment.

The results are an engine capability investigation, not authorization to route production exports through OpenPDF.
