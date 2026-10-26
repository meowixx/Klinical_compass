$ErrorActionPreference = 'Stop'
if (-not (Get-Command ollama -ErrorAction SilentlyContinue) -and -not (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe")) {
    winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
}
& (Join-Path $PSScriptRoot 'start-ai.ps1')
