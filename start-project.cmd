@echo off
chcp 65001 >nul
cd /d "%~dp0"
if /I "%~1"=="stop" goto :stop

if not exist "%~dp0.venv\Scripts\python.exe" goto :setup
if not exist "%~dp0clinical-compass\node_modules" goto :setup
goto :start

:setup
echo First launch: installing required components...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-project.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Read the message above and run SETUP_AND_START.cmd again.
  pause
  exit /b 1
)

:start

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-project.ps1" -Quiet
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-ai.ps1"
start "Clinical Compass API" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\start-backend.ps1"
for /L %%I in (1,1,60) do (
  if exist "%~dp0.venv\Scripts\python.exe" goto :python_ready
  timeout /t 1 /nobreak >nul
)
:python_ready
start "Clinical Compass Web" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\start-frontend.ps1"
start "Clinical Compass MAX Bot" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\start-max-bot.ps1"
powershell.exe -NoProfile -Command "$deadline=(Get-Date).AddSeconds(90); while((Get-Date)-lt $deadline){try{if((Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3125' -TimeoutSec 2).StatusCode -eq 200){exit 0}}catch{}; Start-Sleep -Seconds 1}; exit 1"
start "" http://127.0.0.1:3125
echo.
echo Clinical Compass is running.
echo [S] Stop FastAPI, website, MAX bot and trained AI adapter
echo [Q] Close this window and keep everything running
choice /C SQ /N /M "Choose: "
if errorlevel 2 goto :end
:stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-project.ps1"
if /I "%~1"=="stop" pause
:end
