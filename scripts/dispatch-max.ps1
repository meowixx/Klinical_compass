$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    throw "Не найдено виртуальное окружение .venv. Сначала установите зависимости backend."
}

& ".venv\Scripts\python.exe" -c "from app.database import SessionLocal; from app.scheduler import dispatch_due_assignments; db=SessionLocal(); print(dispatch_due_assignments(db)); db.close()"
