$ErrorActionPreference = "Stop"

$experimentRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$targetRoot = Join-Path $experimentRoot "target\office-investigation"
$qpdfOutput = & (Join-Path $PSScriptRoot "bootstrap-qpdf.ps1")
$qpdf = $qpdfOutput | Select-Object -Last 1

Push-Location $experimentRoot
try {
    & mvn -q -DskipTests compile exec:java '-Dexec.args=office-investigation'
    if ($LASTEXITCODE -ne 0) {
        throw "Office investigation generation failed"
    }

    $manifestPath = Join-Path $targetRoot "pdfjs-inputs.json"
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    $pdfPaths = @($manifest | ForEach-Object path)
    & node (Join-Path $PSScriptRoot "extract-pdfjs.mjs") `
        --output (Join-Path $targetRoot "pdfjs-text-results.json") @pdfPaths
    if ($LASTEXITCODE -ne 0) {
        throw "PDF.js office extraction failed"
    }

    $qpdfChecks = foreach ($case in $manifest) {
        $checkOutput = & $qpdf --check --warning-exit-0 -- $case.path 2>&1
        [ordered]@{
            id = $case.id
            exitCode = $LASTEXITCODE
            output = @($checkOutput)
        }
    }
    $failedQpdf = @($qpdfChecks | Where-Object exitCode -ne 0)
    $qpdfJson = $qpdfChecks | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText(
        (Join-Path $targetRoot "qpdf-check-results.json"),
        $qpdfJson + [Environment]::NewLine)
    if ($failedQpdf.Count -ne 0) {
        throw "qpdf rejected $($failedQpdf.Count) office investigation case(s)"
    }

    $source = Join-Path $experimentRoot "target\fixtures\office-style.pdf"
    $derivative = Join-Path $targetRoot "D-office-overlay.pdf"
    & $qpdf --qdf --object-streams=disable -- $source (Join-Path $targetRoot "A-original-qdf.pdf")
    if ($LASTEXITCODE -ne 0) {
        throw "qpdf could not expand the original office fixture"
    }
    & $qpdf --qdf --object-streams=disable -- $derivative (Join-Path $targetRoot "D-office-overlay-qdf.pdf")
    if ($LASTEXITCODE -ne 0) {
        throw "qpdf could not expand the office derivative"
    }
    $pageObjects = @(
        "SOURCE"
        (& $qpdf --show-pages -- $source)
        "DERIVATIVE"
        (& $qpdf --show-pages -- $derivative)
    ) -join [Environment]::NewLine
    [System.IO.File]::WriteAllText(
        (Join-Path $targetRoot "qpdf-page-objects.txt"),
        $pageObjects + [Environment]::NewLine)

    & mvn '-Dtest=OfficeExtractionInvestigationTest' test
    if ($LASTEXITCODE -ne 0) {
        throw "Office extraction regression test failed"
    }
} finally {
    Pop-Location
}
