param(
    [string]$DevToolsCli = 'C:\微信web开发者工具\cli.bat',
    [switch]$SkipDevTools,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repo 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$mini = Join-Path $repo 'miniprogram'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing backend virtualenv. Follow the installation commands in README.md.'
}
foreach ($tool in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing $tool in PATH." }
}
& $python -c 'import uvicorn, fastapi, sqlalchemy, alembic, httpx, aiohttp, yt_dlp'
if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies are incomplete.' }
if ($CheckOnly) {
    Write-Output 'Local prerequisites PASS. No files or settings changed.'
    exit 0
}
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is already in use. Keep the existing service, or stop it yourself before starting.'
}

$projectConfig = Join-Path $mini 'project.config.json'
if (-not (Test-Path -LiteralPath $projectConfig)) {
    Copy-Item -LiteralPath (Join-Path $mini 'project.config.json.example') -Destination $projectConfig
}
if (-not $SkipDevTools -and (Test-Path -LiteralPath $DevToolsCli)) {
    # The CLI may return exit code 0 even when the IDE requires login.
    $ideOutput = & $DevToolsCli open --project $mini 2>&1
    if ($LASTEXITCODE -ne 0 -or ($ideOutput -join "`n") -match '\[error\]') {
        Write-Warning 'Open the Mini Program project manually in WeChat DevTools; sign in if requested.'
    } else {
        Write-Output 'WeChat DevTools project opened.'
    }
} elseif (-not $SkipDevTools) {
    Write-Warning 'DevTools CLI not found. Open miniprogram manually or pass -DevToolsCli.'
}

# Development identity only. Media parsing/downloads use the real backend.
# Separate data paths preserve any existing application or production database.
$localEnvironment = @{
    APP_ENV = 'development'
    MOCK_WECHAT_AUTH = 'true'
    DEV_BYPASS_DOWNLOAD_ENTITLEMENT = 'false'
    DOWNLOAD_ACCESS_MODE = 'free'
    DOUYIN_SESSION_ENABLED = 'false'
    WECHAT_APP_ID = ''
    WECHAT_APP_SECRET = ''
    APP_TOKEN_SECRET = ([Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N'))
    DATABASE_URL = 'sqlite:///./data/local-preview.db'
    TEMP_DIR = './tmp/local-preview'
    PUBLIC_BASE_URL = 'http://127.0.0.1:8000'
}
$previous = @{}
try {
    foreach ($name in $localEnvironment.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $localEnvironment[$name], 'Process')
    }
    Push-Location $backend
    try {
        Write-Output 'Local development API: http://127.0.0.1:8000/api/v1/health'
        Write-Output 'Identity is simulated; extraction is real. Ctrl+C stops this server.'
        & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
        if ($LASTEXITCODE -ne 0) { throw 'Local API stopped with an error.' }
    } finally { Pop-Location }
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
