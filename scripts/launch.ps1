Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$mode = if ([string]::IsNullOrWhiteSpace($env:SSH_IT_LAUNCH_MODE)) {
    "auto"
} else {
    $env:SSH_IT_LAUNCH_MODE.ToLowerInvariant()
}

if ($mode -notin @("auto", "bundle", "source")) {
    [Console]::Error.WriteLine("SSH_IT_LAUNCH_MODE must be auto, bundle, or source")
    exit 64
}

$bundlePath = Join-Path $repoRoot "dist\SSH It\SSH It.exe"
if ($mode -ne "source" -and (Test-Path -LiteralPath $bundlePath -PathType Leaf)) {
    & $bundlePath @args
    exit $LASTEXITCODE
}

if ($mode -eq "bundle") {
    [Console]::Error.WriteLine("SSH It native Windows bundle not found: $bundlePath")
    exit 69
}

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    Push-Location $repoRoot
    try {
        & $venvPython -m ssh_it @args
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    exit $exitCode
}

$uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
if ($null -ne $uv) {
    Push-Location $repoRoot
    try {
        & $uv.Source run --frozen --no-sync ssh-it @args
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    exit $exitCode
}

[Console]::Error.WriteLine("SSH It is not built and no prepared source environment was found.")
[Console]::Error.WriteLine("Run: uv sync --locked")
exit 69
