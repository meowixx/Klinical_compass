@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Clinical Compass - model evaluation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\evaluate-model.ps1" %*
set "CHECK_EXIT=%ERRORLEVEL%"
echo.
echo Evaluation finished with exit code %CHECK_EXIT%. Read the report path above.
pause
exit /b %CHECK_EXIT%
