$ErrorActionPreference = "Stop"

$version = "12.3.2"
$expectedSha256 = "8941870a604e7c87ed24566b038d46c24ce76616254d2383c578f60c0677f202"
$experimentRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$toolsRoot = Join-Path $experimentRoot ".tools"
$destination = Join-Path $toolsRoot "qpdf"
$qpdfExe = Join-Path $destination "bin\qpdf.exe"

if (Test-Path -LiteralPath $qpdfExe -PathType Leaf) {
    Write-Output $qpdfExe
    exit 0
}

New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
$archive = Join-Path $toolsRoot "qpdf-$version-msvc64.zip"
$expanded = Join-Path $toolsRoot "qpdf-$version-expanded"
$url = "https://github.com/qpdf/qpdf/releases/download/v$version/qpdf-$version-msvc64.zip"

if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    Invoke-WebRequest -Uri $url -OutFile $archive -Headers @{ "User-Agent" = "Claros-OpenPDF-hostile-spike" }
}
$actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
    throw "qpdf archive checksum mismatch"
}

New-Item -ItemType Directory -Force -Path $expanded | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $expanded -Force
$expandedQpdf = Get-ChildItem -LiteralPath $expanded -Recurse -Filter "qpdf.exe" -File |
    Where-Object { $_.Directory.Name -eq "bin" } |
    Select-Object -First 1
if (-not $expandedQpdf) {
    throw "qpdf.exe was not present in the verified archive"
}
$packageRoot = Split-Path -Parent $expandedQpdf.Directory.FullName
$resolvedTools = [System.IO.Path]::GetFullPath($toolsRoot)
$resolvedPackage = [System.IO.Path]::GetFullPath($packageRoot)
if (-not $resolvedPackage.StartsWith($resolvedTools, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to copy qpdf from outside the experiment tools directory"
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -Path (Join-Path $packageRoot "*") -Destination $destination -Recurse -Force
if (-not (Test-Path -LiteralPath $qpdfExe -PathType Leaf)) {
    throw "qpdf bootstrap did not create the expected local executable"
}
Write-Output $qpdfExe
