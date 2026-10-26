$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $projectRoot '.venv-ai'
$python = Join-Path $venv 'Scripts\python.exe'
$modelRoot = Join-Path $projectRoot 'models'
$manifest = Join-Path $projectRoot 'config\ai_judge_models.json'

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 --version *> $null
        if ($LASTEXITCODE -eq 0) { return @('py', '-3.12') }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @('python') }
    throw 'Python 3.11 or 3.12 is required.'
}

Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath $python)) {
    $launcher = Find-Python
    Write-Host 'Creating isolated .venv-ai environment...' -ForegroundColor Cyan
    if ($launcher.Count -eq 2) { & $launcher[0] $launcher[1] -m venv $venv } else { & $launcher[0] -m venv $venv }
}

& $python -m pip install --disable-pip-version-check --upgrade pip
Write-Host 'Installing CPU judge dependencies...' -ForegroundColor Cyan
& $python -m pip install --disable-pip-version-check torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
& $python -m pip install --disable-pip-version-check -r requirements-ai-judge.txt

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw 'Ollama is not installed. Run SETUP_AND_START.cmd first.'
}
$modelConfig = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json
foreach ($ollamaModel in $modelConfig.ollama.PSObject.Properties.Value) {
    Write-Host "Downloading $ollamaModel for Ollama..." -ForegroundColor Cyan
    & ollama pull $ollamaModel
    if ($LASTEXITCODE -ne 0) { throw "Could not download $ollamaModel." }
}

New-Item -ItemType Directory -Path $modelRoot -Force | Out-Null
$env:HF_HOME = Join-Path $modelRoot '.cache'
& $python scripts/download-ai-models.py $projectRoot $manifest
if ($LASTEXITCODE -ne 0) { throw 'Hugging Face model download failed.' }

Write-Host 'Building the clinical guideline search index...' -ForegroundColor Cyan
& $python -m ai_judge.cli build-index
if ($LASTEXITCODE -ne 0) { throw 'Index build failed.' }
& $python -m ai_judge.cli doctor
Write-Host 'Local AI judge is ready.' -ForegroundColor Green
