# OpenPDF hostile-PDF results

## Decision

The `office` failure is caused by OpenPDF 3.0.5's default FOP-backed glyph-substitution path for newly written text. It does **not** alter the source word: the original, open/write-only derivative, and unrelated-overlay derivative all retain and extract the source `office`. The failing overlay substitutes Noto Sans's `ffi` glyph and emits a one-character ToUnicode mapping, so independent extractors correctly follow the malformed semantic mapping and return `ofce`.

Disabling glyph substitution through OpenPDF's public document configuration fixes all minimized Latin cases while retaining Identity-H, Unicode, font embedding, font subsetting, physical placement, and source preservation. The fixed full corpus has 31 PASS and 2 pre-existing RTL PARTIAL verdicts; all 33 preservation, placement, qpdf, and PDF.js render checks remain green. No production code was changed.

## Run context

- Focused investigation: 2026-09-05, branch `codex/claros-v2-nerdy`.
- The initial experiment was preserved and pushed first as `e5c15d8bc79b01b097564af674439c6f44b8fa98` (`test: add OpenPDF hostile PDF evaluation harness`).
- Main baseline inspected read-only: `origin/main` at `5fb217715e4b3278f21a882b2652d928f2cca628`.
- OpenPDF 3.0.5, Apache FOP 2.11, Apache PDFBox 3.0.8, qpdf 12.3.2, PDF.js 4.8.69, Playwright 1.58.2, Microsoft OpenJDK 21.0.10, Windows 11 amd64.
- Fixed full run: 33 source PDFs / 122 pages and 33 derivatives / 125 pages; 176,639 source bytes and 626,886 derivative bytes.
- Structured evidence is generated under `target/office-investigation/` and `target/evidence/`; generated files are ignored rather than committed.

## 1. Baseline: what does the original extract?

**The original extracts `office`, not `ofce`.** This is independently true in all extractors exercised before OpenPDF touches it:

| Extractor | Untouched `office-style.pdf` result |
|---|---|
| PDFBox 3.0.8 `PDFTextStripper` | `Synthetic equivalent - not exported by an office suite` |
| PDF.js 4.8.69 `getTextContent()` | `Synthetic equivalent - not exported by an office suite` |
| pypdf 6.17.0 `extract_text()` | `Synthetic equivalent - not exported by an office suite` |

qpdf QDF expansion confirms the source content itself is a literal WinAnsi Type1 Helvetica string:

```pdf
/F2 8 Tf
42 30 Td
(Synthetic equivalent - not exported by an office suite) Tj
```

The fixture's “office-style” layout is incidental. It is a project-authored synthetic PDFBox fixture, not a file exported by an office suite.

## 2. A/B/C/D separation

The four cases use the same immutable source. B, C, and D use incremental `PdfStamper`; metadata updates and implicit rotated-content handling are disabled.

| Case | Operation | PDFBox extraction | PDF.js extraction | Source content stream |
|---|---|---|---|---|
| A | Original, untouched | source contains `office` | source contains `office` | SHA-256 `a483981c…30b81` |
| B | OpenPDF open/write, no new content | source contains `office` | source contains `office` | same decoded SHA-256 |
| C | Stamp unrelated `CLAROS marker` | source contains `office`; marker exact | source contains `office`; marker exact | same decoded SHA-256 plus wrapper/overlay streams |
| D | Stamp `CLAROS office overlay` | source contains `office`; overlay is `CLAROS ofce overlay` | source contains `office`; overlay is `CLAROS ofce overlay` | same decoded SHA-256 plus wrapper/overlay streams |

The source file SHA-256 remains `543a1148…952be` throughout. OpenPDF therefore does not mutate the existing source extraction. It generates faulty extraction semantics only when its new text contains a font ligature.

## 3. Minimized reproduction and trigger matrix

The minimized source is one Letter page with one independent PDFBox/Helvetica line (`minimal source`). Each derivative stamps the seven required words with one configuration change at a time.

| Case | Extracted words | Result |
|---|---|---|
| Noto Sans, Identity-H, embedded subset, default FOP substitution | `ofce`, `ofcial`, `efcient`, `fle`, `frst`, `afnity`, `diferent` | Reproduces |
| Same, font subsetting disabled | same faulty strings | Reproduces; subsetting is not the trigger |
| Same, full rewrite instead of incremental stamp | same faulty strings | Reproduces; stamping mode/content copying is not the trigger |
| Noto Sans Math, Identity-H | all seven exact | No relevant Latin GSUB ligature substitution |
| Noto Sans, WinAnsi | all seven exact | Avoids the Unicode Type0 path, but is not a Unicode-safe fix |
| Noto Sans, Identity-H, `setGlyphSubstitutionEnabled(false)` | all seven exact | Safe candidate fix for covered non-RTL text |

The word pattern identifies three Noto Sans glyphs:

- glyph/CID `0x0673` (1651), font glyph `f_f`;
- glyph/CID `0x0674` (1652), font glyph `fi`;
- glyph/CID `0x0676` (1654), font glyph `f_f_i`.

Every missing sequence is explained by one substituted glyph extracting as one `f`: `ffi -> f`, `fi -> f`, and `ff -> f`. FontTools inspection of the pinned Noto Sans font confirms those glyph IDs. No unrelated source/font characteristic is required.

## 4. Exact PDF structure failure

The source page uses `/Helvetica` and `/Helvetica-Bold`, `/Subtype /Type1`, and `/Encoding /WinAnsiEncoding`. It has no `/Differences` array or ToUnicode CMap. In D, those source font dictionaries and the decoded source stream remain present. OpenPDF adds a separate page resource:

```pdf
/Xi0 <<
  /BaseFont /XTHHUE+NotoSans-Regular
  /Subtype /Type0
  /Encoding /Identity-H
  /DescendantFonts [ ... /Subtype /CIDFontType2 /CIDToGIDMap /Identity ... ]
  /ToUnicode ...
>>
```

The overlay content stream encodes `ffi` as the single CID `0676`:

```pdf
<0026002f00240035003200360003005206760046004800030052005900480055004f0044005c>Tj
```

Across D and the minimized word matrix, the generated ToUnicode CMaps state:

```pdf
<0673><0673><0066>
<0674><0674><0066>
<0676><0676><0066>
```

These are one-code-point mappings to `f`, not `ff`, `fi`, and `ffi`. qpdf reports a structurally valid PDF because this is a semantic CMap error, not broken PDF syntax.

The OpenPDF source path explains how it is produced:

1. [`FontDetails.convertToBytes`](https://github.com/LibrePDF/OpenPDF/blob/3.0.5/openpdf-core/src/main/java/org/openpdf/text/pdf/FontDetails.java) selects `FopGlyphProcessor` for an Identity-H TrueType font when glyph substitution is enabled and FOP is present.
2. [`FopGlyphProcessor.convertToBytesWithGlyphs`](https://github.com/LibrePDF/OpenPDF/blob/3.0.5/openpdf-core/src/main/java/org/openpdf/text/pdf/FopGlyphProcessor.java) receives FOP's multi-character glyph association, takes only `association.getStart()`, reads one `originalChar`, and stores one Unicode scalar in `longTag`.
3. The font writer builds the ToUnicode map from that one-scalar entry. The data structure cannot represent the full source sequence for the substituted glyph.

This locates the defect in OpenPDF's generated overlay font semantics. It is not caused by the source CMap, source glyph IDs, source encoding, font subsetting, resource copying, incremental stamping, or full content-stream rewriting.

qpdf page inspection also shows the incremental derivative retains page object `4 0 R` and source content object `6 0 R`, adding only wrapper objects `16 0 R` and `17 0 R`. PDFBox's decoded stream hash independently confirms object 6's content is unchanged.

## 5. Candidate fix and preservation rerun

[`Document.setGlyphSubstitutionEnabled(false)`](https://github.com/LibrePDF/OpenPDF/blob/3.0.5/openpdf-core/src/main/java/org/openpdf/text/Document.java) is a public OpenPDF configuration, not a patch. The experiment applies it narrowly:

- normal overlays: set false on the `PdfContentByte` document before `showText`;
- continuation generation: set false on the new `Document` before layout;
- current RTL probes: retain substitution because those scripts require shaping and remain separately classified PARTIAL.

With substitution disabled, the `office` stream contains separate glyphs:

```pdf
<005200490049004c00460048>Tj
```

Its ToUnicode CMap maps those glyphs individually; it contains none of the faulty `0673`, `0674`, or `0676` entries. PDFBox and PDF.js both recover all seven minimized words exactly. Noto Sans remains embedded, subset, Type0, Identity-H, so the fix does not fall back to a limited encoding or rasterization.

The post-fix full run re-exercised all prior checks. Results:

- Maven: 6 tests, 0 failures, including the new root-cause regression.
- OpenPDF: 33/33 derivatives created and reopened.
- qpdf: 33/33 source and derivative checks passed.
- PDF.js: 33/33 derivatives and 125/125 pages reopened/rendered; the office overlay now extracts exactly.
- Physical coordinates: 33/33 passed, including rotations, offset CropBox, and UserUnit.
- Source semantics: 33/33 passed for page boxes/rotation, forms, annotations, links, outlines, metadata/XMP, encryption/permissions, source embedded fonts, images, vector/raster comparison, and immutable source SHA-256.
- Continuation: three pages appended; exact question ID, question, answer order, wrapping, and numbering passed.

No workaround rasterizes, recreates, approximately positions, or silently drops a page or object. Unsupported glyphs and validator disagreements still fail closed.

## 6. RTL scope

No RTL corpus expansion or architecture work was performed. The existing status is unchanged:

- Arabic: source preservation, physical placement, qpdf validity, and PDF.js rendering PASS. PDFBox returns the logical text, while PDF.js exposes presentation-form characters; shaping/order is not machine-proven. Unicode correctness remains PARTIAL.
- Hebrew: source preservation, physical placement, qpdf validity, PDF.js rendering, and logical extraction PASS. Shaping/order is not linguistically certified, so Unicode correctness remains PARTIAL.

Thus the PARTIAL result concerns generated-text shaping/extraction certification. It does not indicate an observed source-preservation or coordinate-placement loss. An integration spike must fail closed for RTL until its shaping and extraction policy is separately proven.

## 7. Untrusted-PDF security boundary

The required design is in [`security-boundary.md`](security-boundary.md). Its minimum boundary is a dedicated, single-job restricted worker/container with no network, non-root execution, read-only runtime/font filesystem, a resolved quota-bound per-job temporary directory, server-created opaque IDs rather than attacker paths, fixed checksum-pinned fonts, no arbitrary HTML/external rendering, and hard input/output/page/memory/CPU/wall-time/process limits. The whole process is killed on timeout and discarded after every job.

The worker has no general storage credentials. Its output is not publishable until a separate restricted validation stage passes OpenPDF/independent reopen, qpdf, structural preservation, exact extraction, physical placement, continuation checks, and output resource limits. All unsupported features, timeouts, parser disagreements, rebuilt-xref cases, and unexpected mutations fail closed.

## Full results table

| Fixture | Open/read | Preserves source | Overlay succeeds | Coordinate correct | Unicode correct | Continuation works | qpdf validation | PDF.js reopen/render | Source losses | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| normal-letter | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| a4 | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| mixed-page-sizes | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| rotated-90 | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| rotated-180 | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| rotated-270 | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| cropbox-offset | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| trim-bleed-boxes | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| mixed-rotations | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| annotations | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| acroform | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| embedded-font | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| unicode-text | PASS | PASS | PASS | PASS | PASS | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| accented-latin | PASS | PASS | PASS | PASS | PASS | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| mathematical-symbols | PASS | PASS | PASS | PASS | PASS | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| cjk | PASS | PASS | PASS | PASS | PASS | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| arabic-rtl | PASS | PASS | PASS | PASS | PARTIAL | NOT APPLICABLE | PASS | PASS | None observed | PARTIAL |
| hebrew-rtl | PASS | PASS | PASS | PASS | PARTIAL | NOT APPLICABLE | PASS | PASS | None observed | PARTIAL |
| long-multiline-answer | PASS | PASS | PASS | PASS | NOT APPLICABLE | PASS | PASS | PASS | None observed | PASS |
| existing-images | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| vector-graphics | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| transparency | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| object-stream-heavy | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| office-style | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| scanned-image-only | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| large-multipage | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| encrypted | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| malformed-readable | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| outlines | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| links | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| metadata | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| user-unit-2 | PASS | PASS | PASS | PASS | NOT APPLICABLE | NOT APPLICABLE | PASS | PASS | None observed | PASS |
| emoji | PASS | PASS | PASS | PASS | PASS | NOT APPLICABLE | PASS | PASS | None observed | PASS |

Overall: 31 PASS and 2 PARTIAL. All 33 preservation, coordinate, qpdf, and PDF.js reopen/render checks passed.

## Commands and actual results

- Before investigation: `mvn test` — 5 tests, 0 failures; commit `e5c15d8` pushed successfully.
- Baseline: PDFBox `PDFTextStripper`, `node scripts/extract-pdfjs.mjs target/fixtures/office-style.pdf`, and pypdf `extract_text()` — all returned source `office`.
- `mvn -q -DskipTests compile exec:java '-Dexec.args=office-investigation'` — emitted 11 A/B/C/D and minimized cases plus structure evidence.
- `node scripts/extract-pdfjs.mjs --output target/office-investigation/pdfjs-text-results.json ...` — all 11 opened; results matched PDFBox exactly.
- qpdf 12.3.2 `--check --warning-exit-0` — exit 0 for all 11 focused cases. `--qdf --object-streams=disable` and `--show-pages` produced the object evidence quoted above.
- `mvn -Dtest=OfficeExtractionInvestigationTest test` — 1 test, 0 failures.
- `scripts/run.ps1` after the fix — exit 0; 6 tests, 0 failures; 33 derivatives; PDF.js rendered 33/33 derivatives; merged report 31 PASS / 2 PARTIAL.
- Production regression baseline, unchanged by this experiment: `.venv/Scripts/python.exe -m pytest backend/tests/document backend/tests/domain/test_export_workflow.py` — 120 passed with 22 existing pypdf deprecation warnings.

## Final report

1. **Capabilities proven:** incremental source manipulation for structurally readable inputs; exact physical overlays across covered boxes/rotations/UserUnit; embedded Identity-H Unicode for covered non-RTL scripts when substitution is disabled; multi-page continuation layout; merging; independent reopen/render/semantic validation.
2. **Failures discovered:** default FOP ligature substitution emits lossy ToUnicode entries for new `ff`, `fi`, and `ffi` glyphs. Arabic/Hebrew shaping certification remains PARTIAL. The malformed-xref fixture requires an explicitly classified full rewrite.
3. **Unexpected mutation:** no measured source feature was unexpectedly mutated in the fixed run. Default non-incremental `PdfStamper` changes Producer metadata unless controlled; this remains a known unsafe default.
4. **Runtime/deployment cost:** OpenPDF requires Java 21+. The measured prospective engine runtime was 33 jars / 20.20 MiB (excluding PDFBox/Jackson validation); the local full JDK was 326.82 MiB. Claros would add a restricted JVM worker/sidecar, dependency patching, health/telemetry, resource enforcement, and cross-runtime failure handling.
5. **Safe ownership:** OpenPDF is proven for the covered incremental source manipulation, non-RTL overlays with substitution disabled, continuation generation, and merging. It is not proven for arbitrary malformed inputs or unrestricted RTL; those paths must be classified and fail closed.
6. **qpdf:** keep it as an independent validator. It catches syntax/stream/encryption problems but does not catch the semantically wrong yet valid ToUnicode mapping, so exact PDFBox and PDF.js extraction gates are also required.
7. **Comparison spike:** a pikepdf/qpdf + PDFKit A/B is not the next required step for this resolved defect. It remains warranted if the isolated production spike cannot preserve these gates under production constraints or if malformed/RTL ownership expands.

**Architecture recommendation:** run an isolated OpenPDF production integration spike behind the threat boundary and the independent validation gate; do not route production exports to it yet.

**B. OpenPDF caused it, but a safe configuration fixes it.**
