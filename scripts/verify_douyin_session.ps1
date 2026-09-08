$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"
$windowsVenvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$posixVenvPython = Join-Path $backendRoot ".venv\bin\python"

if (Test-Path -LiteralPath $windowsVenvPython -PathType Leaf) {
    $python = $windowsVenvPython
} elseif (Test-Path -LiteralPath $posixVenvPython -PathType Leaf) {
    $python = $posixVenvPython
} else {
    $python = "python"
}

try {
    Push-Location -LiteralPath $backendRoot
    $lines = @(& $python -m app.douyin_session.verify 2>$null)
    $exitCode = $LASTEXITCODE
    $jsonLine = $lines | Where-Object { $_ -is [string] -and $_.Trim().StartsWith("{") } | Select-Object -Last 1
    if (-not $jsonLine) {
        Write-Output '{"verification":"failure","outcome":"failure","error_code":"VERIFY_OUTPUT_MISSING"}'
        exit 2
    }
    $null = $jsonLine | ConvertFrom-Json -ErrorAction Stop
    Write-Output $jsonLine.Trim()
    exit $exitCode
} catch {
    Write-Output '{"verification":"failure","outcome":"failure","error_code":"VERIFY_LAUNCH_FAILED"}'
    exit 2
} finally {
    Pop-Location -ErrorAction SilentlyContinue
}
