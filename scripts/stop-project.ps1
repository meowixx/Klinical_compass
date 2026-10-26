param([switch]$Quiet)

$ErrorActionPreference = 'SilentlyContinue'
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$runDirectory = Join-Path $projectRoot '.run'
$all = @(Get-CimInstance Win32_Process)
$rootIds = [System.Collections.Generic.HashSet[int]]::new()

foreach ($process in $all) {
    $command = [string]$process.CommandLine
    if ($command.IndexOf($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
    if (
        $command -match 'scripts[\\/]start-(backend|frontend|max-bot)\.ps1' -or
        $command -match 'uvicorn\s+app\.main:app' -or
        $command -match 'app\.max_polling' -or
        $command -match 'training[\\/]serve_adapter\.py' -or
        $command -match 'clinical-compass[\\/]node_modules[\\/]next'
    ) {
        [void]$rootIds.Add([int]$process.ProcessId)
    }
}

foreach ($pidFile in @('backend.pid', 'frontend.pid', 'max-bot.pid', 'ai-adapter.pid')) {
    $path = Join-Path $runDirectory $pidFile
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $savedPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $path -Raw).Trim(), [ref]$savedPid)) {
        $savedProcess = $all | Where-Object { $_.ProcessId -eq $savedPid } | Select-Object -First 1
        $savedCommand = [string]$savedProcess.CommandLine
        if ($savedProcess -and $savedCommand.IndexOf($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            [void]$rootIds.Add($savedPid)
        }
    }
}

$targetIds = [System.Collections.Generic.HashSet[int]]::new()
foreach ($id in $rootIds) { [void]$targetIds.Add($id) }
do {
    $added = $false
    foreach ($process in $all) {
        if ($targetIds.Contains([int]$process.ParentProcessId) -and -not $targetIds.Contains([int]$process.ProcessId)) {
            [void]$targetIds.Add([int]$process.ProcessId)
            $added = $true
        }
    }
} while ($added)

$stopped = 0
foreach ($process in ($all | Where-Object { $targetIds.Contains([int]$_.ProcessId) } | Sort-Object ProcessId -Descending)) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    $stopped++
}

if (Test-Path -LiteralPath $runDirectory) {
    foreach ($pidFile in @('backend.pid', 'frontend.pid', 'max-bot.pid', 'ai-adapter.pid')) {
        $path = Join-Path $runDirectory $pidFile
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
}

if (-not $Quiet) {
    if ($stopped) {
        Write-Host "Clinical Compass stopped ($stopped processes)." -ForegroundColor Green
    } else {
        Write-Host 'Clinical Compass processes were not running.' -ForegroundColor Yellow
    }
}
