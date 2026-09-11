$ErrorActionPreference = "Stop"

$experimentRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$qpdfOutput = & (Join-Path $PSScriptRoot "bootstrap-qpdf.ps1")
$env:OPENPDF_QPDF = $qpdfOutput | Select-Object -Last 1

Push-Location $experimentRoot
try {
    & mvn test
    if ($LASTEXITCODE -ne 0) { throw "Maven tests failed" }

    & mvn exec:java "-Dexec.args=run"
    if ($LASTEXITCODE -ne 0) { throw "OpenPDF harness run failed" }

    & node "scripts/validate-pdfjs.mjs" "target/evidence/pdfjs-cases.json" "target/evidence/pdfjs-results.json"
    if ($LASTEXITCODE -ne 0) { throw "PDF.js validation failed" }

    & mvn exec:java "-Dexec.args=report"
    if ($LASTEXITCODE -ne 0) { throw "Evidence report generation failed" }
} finally {
    Pop-Location
}

