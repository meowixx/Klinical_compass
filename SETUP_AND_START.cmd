@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Clinical Compass Setup

echo Preparing Clinical Compass for this computer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-project.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Read the message above, then run this file again.
  pause
  exit /b 1
)

call "%~dp0start-project.cmd"
