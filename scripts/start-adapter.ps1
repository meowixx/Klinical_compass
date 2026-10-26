$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$profilePath = Join-Path $projectRoot 'config\ai_runtime.local.json'
$profile = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $profile.enabled) { throw 'Local adapter is not enabled.' }
$python = Join-Path $projectRoot '.venv-training\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Training Python environment is missing. See training\README.md.' }
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:11435/health' -TimeoutSec 2
    if ($health.model -eq $profile.model -and $health.adapterSha256 -eq $profile.adapterSha256) {
        Write-Host 'Trained adapter is already running.' -ForegroundColor Green
        exit 0
    }
    throw 'Port 11435 is occupied by a different adapter.'
} catch {
    if ($_.Exception.Message -like '*different adapter*') { throw }
}
$logs = Join-Path $projectRoot 'training\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    $fallback = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $fallback) { $ollama = Get-Item -LiteralPath $fallback }
}
if ($ollama) {
    $ollamaPath = if ($ollama.Source) { $ollama.Source } else { $ollama.FullName }
    & $ollamaPath stop qwen3:4b-instruct 2>$null | Out-Null
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$entry = Join-Path $projectRoot 'training\serve_adapter.py'
$worker = Start-Process -FilePath $python -ArgumentList @('-u', ('"' + $entry + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs "adapter-$stamp.out.log") -RedirectStandardError (Join-Path $logs "adapter-$stamp.err.log")
$deadline = (Get-Date).AddSeconds(180)
do {
    Start-Sleep -Seconds 1
    $worker.Refresh()
    if ($worker.HasExited) { throw "Adapter failed to start. Read training\logs\adapter-$stamp.err.log" }
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:11435/health' -TimeoutSec 2
        if ($health.model -eq $profile.model -and $health.adapterSha256 -eq $profile.adapterSha256) {
            Write-Host 'Trained Qwen adapter: ready on 127.0.0.1:11435' -ForegroundColor Green
            exit 0
        }
    } catch {}
} while ((Get-Date) -lt $deadline)
throw 'Adapter startup timed out. Check training\logs before restarting.'
