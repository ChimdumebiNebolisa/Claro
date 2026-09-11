# OpenPDF validator-minimization spike

This experiment consumes the preserved hostile-corpus and integration spikes. It does not change Claros production behavior. Its scope is deliberately limited to PDF correctness, validator differential behavior, and sequential export latency.

The evidence runner creates test-only corrupted derivatives from synthetic PDFs, runs qpdf, PDFBox, and PDF.js independently, profiles the existing one-open PDFBox validator, and benchmarks three publication-gate variants:

- `full`: qpdf + PDFBox + PDF.js/Chromium
- `qpdf_pdfbox`: qpdf + PDFBox
- `pdfbox_only`: PDFBox alone, for comparison only

Generated PDFs and job directories are disposable and ignored. Only aggregate, content-free evidence is checked in.

## Run

```powershell
mvn -q -f experiments/openpdf-integration/pom.xml package -DskipTests
.venv/Scripts/python.exe experiments/openpdf-validation/run-evidence.py
.venv/Scripts/python.exe -m pytest -q experiments/openpdf-validation/tests
```

The runner requires only dependencies already used by Claros and the earlier spikes. It does not download fixtures or add another renderer.

See [`results.md`](results.md) for the measured validator matrix, gate decision,
PDFBox profile, and realistic document-size benchmarks.
