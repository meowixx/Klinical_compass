@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Clinical Compass - Qwen QLoRA training
echo Clinical Compass: local Qwen adapter training
echo First run downloads Python packages and the original model weights.
echo Close games and other GPU applications before training.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\train-model.ps1" %*
set "TRAIN_EXIT=%ERRORLEVEL%"
echo.
if "%TRAIN_EXIT%"=="0" (
  echo Command completed. Read the result and output path above.
) else (
  echo Training did not complete. See the error above and training\logs.
)
pause
exit /b %TRAIN_EXIT%
