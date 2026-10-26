param([string]$Run)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv-training\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Training environment is missing. Run TRAIN_MODEL.cmd -CheckOnly first.' }
if (-not $Run) {
    $completed = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'training\runs') -Directory | Sort-Object Name -Descending | Where-Object {
        $resultFile = Join-Path $_.FullName 'result.json'
        (Test-Path -LiteralPath $resultFile) -and ((Get-Content -LiteralPath $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json).status -eq 'completed')
    } | Select-Object -First 1
    if (-not $completed) { throw 'No completed training runs found.' }
    $Run = $completed.FullName
}
try {
    Invoke-RestMethod 'http://127.0.0.1:11435/health' -TimeoutSec 2 | Out-Null
    throw 'The adapter server is using the GPU. Stop the project before evaluation, then restart it afterwards.'
} catch {
    if ($_.Exception.Message -like '*using the GPU*') { throw }
}
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
& $python (Join-Path $projectRoot 'training\evaluate_adapter.py') --run $Run
exit $LASTEXITCODE
