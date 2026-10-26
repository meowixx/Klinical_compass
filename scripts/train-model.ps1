param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$trainingRoot = Join-Path $projectRoot 'training'
$python = Join-Path $projectRoot '.venv-training\Scripts\python.exe'
$logs = Join-Path $trainingRoot 'logs'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = Join-Path $trainingRoot 'cache'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$env:WANDB_DISABLED = 'true'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$logPath = Join-Path $logs ('launcher-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$resultCode = 0
Start-Transcript -LiteralPath $logPath | Out-Null
try {
    $gpu = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $gpu) { throw 'NVIDIA driver was not found. Install an NVIDIA driver before training.' }
    & $gpu.Source --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader
    if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi failed. Check the NVIDIA driver.' }

    $diskRoot = [System.IO.Path]::GetPathRoot($projectRoot)
    $disk = [System.IO.DriveInfo]::new($diskRoot)
    if ($disk.AvailableFreeSpace -lt 25GB) {
        throw 'At least 25 GB of free disk space is required for the first setup and model cache.'
    }

    if (-not (Test-Path -LiteralPath $python)) {
        $basePython = $null
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            foreach ($version in @('-3.12', '-3.11')) {
                try {
                    $candidate = & $launcher.Source $version -c 'import sys; print(sys.executable)' 2>$null
                    if ($LASTEXITCODE -eq 0 -and $candidate) { $basePython = @($candidate)[-1]; break }
                } catch { continue }
            }
        }
        if (-not $basePython) {
            $candidate = Get-Command python -ErrorAction SilentlyContinue
            if ($candidate) {
                try {
                    $versionText = & $candidate.Source --version 2>$null
                    if ($LASTEXITCODE -eq 0 -and $versionText -match '^Python 3\.(11|12)\.') { $basePython = $candidate.Source }
                } catch { $basePython = $null }
            }
        }
        if (-not $basePython) {
            throw 'Install Python 3.12 (64 bit), then run TRAIN_MODEL.cmd again. Download: https://www.python.org/downloads/windows/'
        }
        Write-Host 'Creating separate .venv-training environment...' -ForegroundColor Cyan
        & $basePython -m venv (Join-Path $projectRoot '.venv-training')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the training environment.' }
    }
    & $python -c 'import sys; assert sys.version_info[:2] in ((3,11),(3,12)) and sys.maxsize > 2**32'
    if ($LASTEXITCODE -ne 0) { throw 'The training environment needs 64-bit Python 3.11 or 3.12.' }

    $requirements = Join-Path $trainingRoot 'requirements.txt'
    $stamp = Join-Path $projectRoot '.venv-training\requirements.sha256'
    $requiredHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    $installedHash = if (Test-Path -LiteralPath $stamp) { (Get-Content -LiteralPath $stamp -Raw).Trim() } else { '' }
    if ($installedHash -ne $requiredHash) {
        Write-Host 'Installing training libraries (first run only)...' -ForegroundColor Cyan
        & $python -m pip install --disable-pip-version-check --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'pip update failed. Check the network connection.' }
        & $python -m pip install --disable-pip-version-check 'torch==2.8.0' --index-url https://download.pytorch.org/whl/cu128
        if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed.' }
        & $python -m pip install --disable-pip-version-check -r $requirements
        if ($LASTEXITCODE -ne 0) { throw 'Training dependencies installation failed.' }
        & $python -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Incompatible training dependencies.' }
        Set-Content -LiteralPath $stamp -Value $requiredHash -Encoding ascii
    }

    Write-Host 'Validating dataset and training setup...' -ForegroundColor Cyan
    & $python (Join-Path $projectRoot 'datasets\clinical_compass_qwen_v6\validate_dataset.py')
    if ($LASTEXITCODE -ne 0) { throw 'Dataset validation failed. Training was not started.' }
    & $python -m unittest discover -s (Join-Path $trainingRoot 'tests') -v
    if ($LASTEXITCODE -ne 0) { throw 'Training pipeline checks failed.' }
    $trainArguments = @((Join-Path $trainingRoot 'train_qwen.py'))
    if ($CheckOnly) { $trainArguments += '--check-only' }
    & $python @trainArguments
    if ($LASTEXITCODE -ne 0) { throw 'Training command failed. The details are above; the site model has not been replaced.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    $resultCode = 1
} finally {
    Stop-Transcript | Out-Null
}
Write-Host "Launcher log: $logPath"
exit $resultCode
