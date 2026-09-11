# OpenPDF validator and latency investigation

Evidence date: 2026-09-06. This is an isolated experiment. It does not change
Claros production behavior. The test mutations below are PDF-correctness
mutations only; no security-boundary, sandbox, network-isolation,
resource-exhaustion, process-limit, egress, filesystem-restriction, or
adversarial-security testing was performed.

## Decision

**A. qpdf + PDFBox is sufficient synchronously; move PDF.js to CI/release
validation.**

Across the required differential corpus, qpdf + PDFBox rejected every known
publication-blocking defect. PDF.js rejected no additional defect that qpdf +
PDFBox accepted. PDF.js remains valuable as an independent browser-renderer
oracle and must remain in CI/release corpus validation; it does not need to
run synchronously for every student export based on this evidence.

No production migration was performed.

## Scope and evidence

The rerun used the existing OpenPDF 3.0.5 worker, PDFBox 3.0.8, qpdf 12.3.2,
PDF.js 4.8.69/Chromium, Java 21, Node 24, the existing fixtures, and generated
derivatives. The aggregate machine-readable evidence is
[`evidence.json`](evidence.json). The experiment harness is
[`run-evidence.py`](run-evidence.py).

The current validator implementation opens source and derivative once per
PDFBox process, extracts ordinary page text once per document, and records
phase timings in `pdfbox-profile.json`. The source-page and continuation
ownership remains in the existing OpenPDF worker.

## 1. Validator differential matrix

`accept`/`reject` is the validator decision. The code after a slash is the
observed failure code where available.

| Case | qpdf | PDFBox | PDF.js |
|---|---|---|---|
| valid control | accept | accept | accept |
| malformed PDF structure | reject / `qpdf_check` | reject / `generated_text_exact` | reject |
| ligature / incorrect ToUnicode | accept | reject / `generated_text_exact` | reject |
| wrong generated text | accept | reject / `generated_text_exact` | reject |
| missing generated text | accept | reject / `source_semantics` | reject |
| incorrect physical coordinates | accept | reject / `placement_exact` | accept |
| page-box mutation | accept | reject / `source_semantics` | accept |
| page rotation mutation | accept | reject / `source_semantics` | accept |
| source content-stream mutation | accept | reject / `source_semantics` | accept |
| annotation mutation | accept | reject / `source_semantics` | accept |
| form mutation | accept | reject / `source_semantics` | accept |
| link mutation | accept | reject / `source_semantics` | accept |
| outline mutation | accept | reject / `source_semantics` | accept |
| continuation-page ordering error | accept | reject / `continuation_content` | accept |
| continuation text error | accept | reject / `continuation_content` | reject |
| valid PDF with wrong committed answer | accept | reject / `generated_text_exact` | reject |
| untouched source returned | accept | reject / `generated_text_exact` | reject |

The full control and all 16 defect cases matched their expected outcomes for
all three gate variants. In particular:

- qpdf caught malformed structure and accepted the semantically wrong but
  structurally valid cases.
- PDFBox caught exact generated-text failures, the OpenPDF ligature mapping
  regression, placement, geometry, source-content/resource preservation,
  annotations/forms/links/outlines, continuation contents/order, wrong
  committed answers, and an untouched source.
- PDF.js caught several text/extraction failures but accepted coordinate,
  geometry, source-preservation, and continuation-order mutations because it
  has no job contract against which to compare those properties.

**Answer to the main question:** no. In this required corpus, PDF.js did not
detect any important publication-blocking defect that qpdf + PDFBox accepted.
This is a tested result, not an assumption; it is not a claim that all future
PDF features are covered by this corpus.

## 2. Gate comparison

Ten sequential small-document exports were run for each variant. Values are
mean / p50 / p95 / max in milliseconds.

| Gate | Total | OpenPDF process | qpdf | PDFBox | PDF.js | Validation |
|---|---:|---:|---:|---:|---:|---:|
| qpdf + PDFBox + PDF.js | 8894 / 8874 / 9193 / 9193 | 1756 / 1748 / 1855 / 1855 | 151 / 132 / 260 / 260 | 2990 / 2973 / 3157 / 3157 | 3842 / 3840 / 4045 / 4045 | 6984 / 6988 / 7345 / 7345 |
| qpdf + PDFBox | **4966 / 4934 / 5265 / 5265** | 1743 / 1738 / 1831 / 1831 | 147 / 134 / 199 / 199 | 2910 / 2894 / 3095 / 3095 | — | **3057 / 3054 / 3228 / 3228** |
| PDFBox only (comparison) | 4888 / 4897 / 5170 / 5170 | 1748 / 1752 / 1837 / 1837 | — | 3025 / 2989 / 3307 / 3307 | — | 3025 / 2989 / 3307 / 3307 |

The historical concurrency-1 baseline was 9194 ms total, with 1781 ms
OpenPDF, 109 ms qpdf, 2797 ms PDFBox, and 3875 ms PDF.js. The candidate gate
therefore removes about 3928 ms versus the current 10-run control mean and
about 4228 ms versus the historical baseline, approximately 44% and 46%
respectively. Retaining qpdf costs only about 78 ms mean versus PDFBox-only in
this run, while preserving an independent structural parser.

### Gate correctness checks

The valid control and production-shaped derivatives were checked for exact
generated-text extraction, committed-answer equality, physical placement,
page geometry, source preservation, continuation content/order, output reopen,
and malformed-output rejection. qpdf + PDFBox passed every valid control and
rejected every required defect above. PDFBox-only also matched the expected
outcomes in this corpus, but is not recommended because qpdf is cheap and
provides independent structural validation.

## 3. PDFBox profile

For the qpdf + PDFBox gate on the small representative export, the mean
PDFBox profile was:

| Phase | Mean ms |
|---|---:|
| JVM/process overhead | 384.8 |
| contract and limits | 683.8 |
| PDF reopen (source + derivative) | 247.0 |
| semantic preservation | 1164.5 |
| source content streams | 11.4 |
| text extraction | 218.9 |
| page geometry | 1.6 |
| generated-text extraction | 44.9 |
| coordinate checks | 5.2 |
| continuation checks | 4.2 |
| raster rendering | 307.3 |
| PDFBox internal total | 2721.2 |

The low-risk consolidation already present in the experiment is material:
source and derivative are opened once, ordinary text is extracted once per
document, and the extracted derivative text is reused for source and
continuation checks. The remaining generated-text pass is intentionally
separate because it temporarily isolates generated content streams to prove
exact placement; removing that pass would weaken the check. The profile does
not justify removing raster rendering from the PDFBox validation contract.

For larger documents, fixed startup/reopen cost remains roughly 0.4/0.25 s,
while page-dependent work dominates:

- 10 source pages / 11 output pages: text extraction 368 ms, rendering 1805
  ms, PDFBox internal total 4457 ms.
- 50 source pages / 59 output pages: text extraction 2823 ms, generated-text
  extraction 962 ms, rendering 4238 ms, PDFBox internal total 10713 ms.

## 4. Realistic document sizes

The following are three sequential qpdf + PDFBox runs per size. Values are
mean / p50 / p95 / max. RSS is the peak RSS of the launched parent process;
it is an observation for sizing, not a security test.

| Size | Source / output pages | Answers | Source / output bytes | Total ms | OpenPDF ms | Validation ms | PDFBox RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Small | 2 / 2 | 3 | 1,890 / 16,595 | 5038 / 5015 / 5144 / 5144 | 1697 / 1708 / 1713 / 1713 | 3242 / 3241 / 3351 / 3351 | 117 MB |
| Medium | 10 / 11 | 9 (1 continuation) | 5,574 / 40,880 | 7044 / 6853 / 7501 / 7501 | 1983 / 1983 / 2018 / 2018 | 4976 / 4766 / 5400 / 5400 | 133 MB |
| Large | 50 / 59 | 33 (3 continuation answers, 9 pages) | 24,039 / 83,683 | 13558 / 13071 / 14946 / 14946 | 2191 / 2200 / 2250 / 2250 | 11265 / 10863 / 12616 / 12616 | 153 MB |

Validation cost is mostly startup/contract/semantic work for the tiny export,
then scales materially with page count, text, generated answers, and rendered
continuation pages. OpenPDF itself grows modestly in this synthetic corpus;
PDFBox is the remaining latency bottleneck after PDF.js is removed from the
synchronous path.

## 5. OpenPDF ownership confirmation

The worker continues to use OpenPDF for both halves of the derivative:

- **Top half:** `PdfReader`/`PdfStamper` preserves arbitrary source pages,
  writes exact coordinate overlays, and retains page geometry/source pages.
- **Bottom half:** OpenPDF creates continuation documents, performs wrapping,
  appends continuation pages, and supplies page numbering/generated content.

No pdfcn, PDFKit, pikepdf, or alternate renderer was introduced. pikepdf was
used only to create test-only mutated derivatives; it never rendered a
published output.

The prior hostile-corpus result remains covered: OpenPDF glyph substitution is
disabled for the tested non-RTL generated text path, which avoids the lossy
`ff`/`fi`/`ffi` ToUnicode mapping. The existing Arabic/Hebrew shaping status
remains PARTIAL and is not expanded by this investigation.

## 6. Regression results

- Validator evidence tests: 3 passed.
- OpenPDF hostile Maven tests: passed; only existing FontBox/FOP warnings.
- OpenPDF integration Maven tests: passed.
- Integration functional pytest suite, excluding the separately scoped
  security-static test: 21 passed, 1 warning.
- Full tracked backend suite: 513 passed, 23 warnings.

No production tests were weakened and no production behavior was changed.

## 7. Recommended architecture

Synchronous export gate:

1. OpenPDF derivative generation.
2. qpdf structural check.
3. PDFBox independent reopen, exact text/answer/placement/geometry/source/
   continuation checks, and the existing PDFBox render/reopen check.
4. Publish only after both synchronous validators pass.

CI/release/corpus compatibility gate:

- PDF.js/Chromium over the hostile-PDF correctness corpus, OpenPDF regression
  corpus, representative exported worksheets, ligature regression, and
  continuation pages.

The exact next architecture step is a separate CI/release PDF.js job consuming
the same immutable derivative fixtures and emitting an independent compatibility
report. A later production change may move PDF.js out of the request path only
after that CI job is in place; this task intentionally does not perform that
migration.

## Remaining uncertainty

The conclusion is bounded by the existing fixtures and generated defect corpus.
PDF.js should remain mandatory for corpus/release compatibility because it is
an independent browser renderer and can expose future parser/rendering gaps.
No unique synchronous defect was found here, so keeping Chromium in every
export would spend approximately 3.8–4.0 seconds per job without improving the
tested publication-blocking guarantees.
