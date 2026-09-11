# Third-party notices

The generated PDFs are synthetic Claros test artifacts covered by the repository's MIT license. No downloaded worksheet content is used.

## OpenPDF

OpenPDF 3.0.5 is consumed from Maven Central under MPL-2.0 or LGPL-2.1-or-later. Project and license details: <https://github.com/LibrePDF/OpenPDF>.

## Apache PDFBox

Apache PDFBox 3.0.8 is used only to generate synthetic fixtures and independently inspect/render results. It is licensed under Apache-2.0: <https://pdfbox.apache.org/>.

## Apache FOP

Apache FOP 2.11 provides OpenPDF's optional complex-script support and is licensed under Apache-2.0: <https://xmlgraphics.apache.org/fop/>.

## Bouncy Castle

Bouncy Castle `bcprov-jdk18on` 1.84 enables the encrypted-PDF probe and is distributed under its MIT-style license: <https://www.bouncycastle.org/about/license/>.

## Noto fonts

Noto Sans, Noto Sans Math, Noto Sans Arabic, Noto Sans Hebrew, Noto Sans SC, and Noto Emoji are licensed under the SIL Open Font License 1.1. Remote files are pinned to Google Fonts commit `5e35378e6bda803962ee6fd257e444a7d459660d` and verified against the SHA-256 values in `FontAssets.java`: <https://github.com/google/fonts/tree/main/ofl>.

## qpdf

qpdf 12.3.2 is an optional local validation executable bootstrapped from its official release archive after SHA-256 verification. qpdf is licensed under Apache-2.0: <https://github.com/qpdf/qpdf>.

## PDF.js and Playwright

The repository's installed PDF.js and Playwright packages provide browser-engine reopen/render checks. PDF.js is Apache-2.0 and Playwright is Apache-2.0.
