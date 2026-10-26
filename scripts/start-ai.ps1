$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$profilePath = Join-Path $projectRoot 'config\ai_runtime.local.json'
if (Test-Path -LiteralPath $profilePath) {
    $profile = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($profile.blocked) {
        Write-Warning 'Trained model failed evaluation. The site will use structured rules. See the evaluation report.'
        exit 0
    }
    if ($profile.enabled) {
        & (Join-Path $PSScriptRoot 'start-adapter.ps1')
        exit $LASTEXITCODE
    }
}
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    $fallback = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $fallback) { $ollama = Get-Item -LiteralPath $fallback }
}
if (-not $ollama) {
    Write-Warning 'Ollama is not installed. Run scripts\setup-ai.ps1.'
    exit 0
}

$ollamaPath = if ($ollama.Source) { $ollama.Source } else { $ollama.FullName }
try { Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null }
catch {
    Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        try { Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null; break } catch {}
    } while ((Get-Date) -lt $deadline)
}

$models = (& $ollamaPath list 2>$null) -join "`n"
if ($models -notmatch 'qwen3:4b-instruct') {
    Write-Host 'Downloading Qwen3-4B Instruct (one time only)...' -ForegroundColor Cyan
    & $ollamaPath pull qwen3:4b-instruct
}
Write-Host 'Qwen3-4B Instruct: ready' -ForegroundColor Green
