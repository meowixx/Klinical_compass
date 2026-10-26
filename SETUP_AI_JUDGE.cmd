@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-ai-judge.ps1"
if errorlevel 1 (
  echo.
  echo AI judge setup failed.
  pause
  exit /b 1
)
echo.
echo AI judge setup completed.
pause
