$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $projectRoot 'clinical-compass'
$runDirectory = Join-Path $projectRoot '.run'

Set-Location -LiteralPath $frontend
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules'))) {
    npm.cmd ci
}

if (-not (Test-Path -LiteralPath (Join-Path $frontend '.env.local'))) {
    Copy-Item -LiteralPath (Join-Path $frontend '.env.example') -Destination (Join-Path $frontend '.env.local')
    $content = Get-Content -LiteralPath (Join-Path $frontend '.env.local') -Raw
    $content = $content.Replace('NEXT_PUBLIC_DATA_SOURCE=mock', 'NEXT_PUBLIC_DATA_SOURCE=api')
    Set-Content -LiteralPath (Join-Path $frontend '.env.local') -Value $content -Encoding utf8
}

Write-Host 'Web: http://127.0.0.1:3125' -ForegroundColor Cyan
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
Set-Content -LiteralPath (Join-Path $runDirectory 'frontend.pid') -Value $PID -Encoding ascii
try {
    npm.cmd run dev -- --port 3125
} finally {
    Remove-Item -LiteralPath (Join-Path $runDirectory 'frontend.pid') -Force -ErrorAction SilentlyContinue
}
