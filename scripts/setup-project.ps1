$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $projectRoot 'clinical-compass'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machinePath;$userPath"
}

function Find-Python {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $null = & $launcher.Source -3.12 --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return [PSCustomObject]@{ FilePath = $launcher.Source; Arguments = @('-3.12') }
        }
    }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $pythonVersion = & $pythonCommand.Source --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $pythonVersion -match 'Python 3\.(1[1-9]|[2-9][0-9])') {
            return [PSCustomObject]@{ FilePath = $pythonCommand.Source; Arguments = @() }
        }
    }
    return $null
}

function Install-WingetPackage([string]$Id, [string]$Name) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "$Name is required, but winget is unavailable. Install $Name and run this file again."
    }
    Write-Host "Installing $Name..." -ForegroundColor Cyan
    winget install --id $Id --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Could not install $Name (winget exit code $LASTEXITCODE)." }
    Refresh-Path
}

Set-Location -LiteralPath $projectRoot
Write-Host 'Clinical Compass: first-time setup' -ForegroundColor Cyan

$pythonCommand = Find-Python
if (-not $pythonCommand) {
    Install-WingetPackage 'Python.Python.3.12' 'Python 3.12'
    $pythonCommand = Find-Python
}
if (-not $pythonCommand) { throw 'Python was installed but is not available. Reopen the terminal and run again.' }

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodeMajor = if ($nodeCommand) { [int]((& node --version).TrimStart('v').Split('.')[0]) } else { 0 }
if ($nodeMajor -lt 20 -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Install-WingetPackage 'OpenJS.NodeJS.LTS' 'Node.js LTS'
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Node.js was installed but npm is not available. Reopen the terminal and run again.'
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Creating isolated Python environment...' -ForegroundColor Cyan
    $pythonArguments = @($pythonCommand.Arguments) + @('-m', 'venv', '.venv')
    & $pythonCommand.FilePath @pythonArguments
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
}

Write-Host 'Installing backend dependencies...' -ForegroundColor Cyan
& $python -m pip install --disable-pip-version-check --upgrade pip
& $python -m pip install --disable-pip-version-check -r requirements.txt

Write-Host 'Installing frontend dependencies...' -ForegroundColor Cyan
Push-Location $frontend
try {
    npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') -Destination (Join-Path $projectRoot '.env')
}

$frontendEnv = Join-Path $frontend '.env.local'
if (-not (Test-Path -LiteralPath $frontendEnv)) {
    Copy-Item -LiteralPath (Join-Path $frontend '.env.example') -Destination $frontendEnv
}
$frontendEnvContent = Get-Content -LiteralPath $frontendEnv -Raw
$updatedFrontendEnv = $frontendEnvContent.Replace('NEXT_PUBLIC_DATA_SOURCE=mock', 'NEXT_PUBLIC_DATA_SOURCE=api')
if ($updatedFrontendEnv -ne $frontendEnvContent) {
    $utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($frontendEnv, $updatedFrontendEnv.TrimEnd() + "`n", $utf8WithoutBom)
}

New-Item -ItemType Directory -Path (Join-Path $projectRoot 'data') -Force | Out-Null
Write-Host 'Creating and seeding SQLite...' -ForegroundColor Cyan
& $python create_tables.py

Write-Host 'Preparing local Qwen model...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'setup-ai.ps1')

Write-Host ''
Write-Host 'Setup completed. Run start-project.cmd.' -ForegroundColor Green
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'BotMax\MaxAPI.txt'))) {
    Write-Host 'MAX bot is optional for the local demo. To enable it, put its API key in BotMax\MaxAPI.txt.' -ForegroundColor Yellow
}
