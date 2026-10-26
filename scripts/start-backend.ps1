$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runDirectory = Join-Path $projectRoot '.run'

Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Python environment .venv was not found. Run SETUP_AND_START.cmd first.'
}

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') -Destination (Join-Path $projectRoot '.env')
}

Write-Host 'FastAPI: http://127.0.0.1:8000' -ForegroundColor Cyan
Write-Host 'Swagger: http://127.0.0.1:8000/docs' -ForegroundColor Cyan
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
Set-Content -LiteralPath (Join-Path $runDirectory 'backend.pid') -Value $PID -Encoding ascii
try {
    & $python -m uvicorn app.main:app --app-dir $projectRoot --host 127.0.0.1 --port 8000
} finally {
    Remove-Item -LiteralPath (Join-Path $runDirectory 'backend.pid') -Force -ErrorAction SilentlyContinue
}
