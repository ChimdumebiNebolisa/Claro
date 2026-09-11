# Claros OpenPDF worker

This maintained worker receives a strict server-created render contract, uses
OpenPDF 3.0.5 for incremental source stamping and attached answer pages, and
uses PDFBox 3.0.8 for the independent semantic, text, geometry, and raster
validation gate. The FastAPI service releases no derivative bytes until this
validator and qpdf both succeed.

Build the shaded Java 21 artifact from the repository root:

```text
mvn -q -f workers/openpdf/pom.xml package -DskipTests
```

The resulting runtime artifact is
`workers/openpdf/target/claros-openpdf-worker-0.1.0-SNAPSHOT-all.jar`.
Production application code does not import or execute code from
`experiments/`.

Generated right-to-left text and PDFs that require OpenPDF to rebuild their
cross-reference structure remain unsupported and fail closed. Noto Sans is
embedded with glyph substitution explicitly disabled for the validated
non-RTL path, preserving `ff`, `fi`, and `ffi` extraction.

See `THIRD_PARTY_NOTICES.md` and `assets/fonts/noto-sans/README.md` for pinned
dependencies and font licensing/checksums.
