param(
    [Parameter(Mandatory = $true)]
    [string]$JobDirectory,
    [string]$Image = "claros-openpdf-worker-spike:local"
)

$ErrorActionPreference = "Stop"
$resolvedJob = (Resolve-Path -LiteralPath $JobDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedJob "job.json") -PathType Leaf)) {
    throw "The server-created job directory is missing job.json"
}
if (-not (Test-Path -LiteralPath (Join-Path $resolvedJob "source.pdf") -PathType Leaf)) {
    throw "The server-created job directory is missing source.pdf"
}

docker run --rm `
    --network none `
    --read-only `
    --cap-drop ALL `
    --security-opt no-new-privileges:true `
    --pids-limit 64 `
    --memory 256m `
    --cpus 1 `
    --user 10001:10001 `
    --tmpfs /tmp/claros:rw,noexec,nosuid,nodev,size=96m `
    --mount "type=bind,source=$resolvedJob,target=/job" `
    $Image
