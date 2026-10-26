$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runDirectory = Join-Path $projectRoot '.run'

Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
if (-not (Test-Path -LiteralPath $python)) {
    Write-Warning 'Python environment .venv was not found. Run SETUP_AND_START.cmd first.'
    exit 0
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'BotMax\MaxAPI.txt'))) {
    Write-Warning 'MAX bot is disabled: BotMax\MaxAPI.txt was not found. The website and FastAPI remain available.'
    exit 0
}

Write-Host 'MAX bot: local Long Polling' -ForegroundColor Cyan
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and $_.CommandLine -like '*-m app.max_polling*'
}
if ($existing) {
    Write-Host 'MAX bot is already running.' -ForegroundColor Yellow
    return
}
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
Set-Content -LiteralPath (Join-Path $runDirectory 'max-bot.pid') -Value $PID -Encoding ascii
try {
    & $python -m app.max_polling
} finally {
    Remove-Item -LiteralPath (Join-Path $runDirectory 'max-bot.pid') -Force -ErrorAction SilentlyContinue
}
