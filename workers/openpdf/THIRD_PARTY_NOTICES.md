# OpenPDF worker third-party notices

The worker build pins these runtime libraries in `pom.xml`:

- OpenPDF 3.0.5 — LGPL-2.1-or-later and MPL-2.0 dual license.
- Apache FOP 2.11 — Apache License 2.0.
- Apache PDFBox 3.0.8 — Apache License 2.0.
- Jackson Databind 2.20.0 — Apache License 2.0.

The shaded artifact retains dependency `META-INF` license and notice resources.
Noto Sans Regular is embedded into generated answer text under the SIL Open
Font License 1.1. Its source, license, and SHA-256 checksum are recorded in
`assets/fonts/noto-sans/README.md` and `assets/fonts/noto-sans/OFL.txt`.

qpdf is an independent executable validator distributed under Apache License
2.0. It is installed separately by the runtime image or by the local bootstrap
script and is not embedded into the worker JAR.
