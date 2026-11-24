@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Set up Python and the virtual environment using operations\README.md first.
  exit /b 1
)
".venv\Scripts\python.exe" manage.py check
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" manage.py migrate --check
if errorlevel 1 (
  echo Database migrations are pending. Back up existing data and follow operations\README.md.
  exit /b 1
)
if "%TRIPATHI_API_PORT%"=="" set "TRIPATHI_API_PORT=8080"
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:%TRIPATHI_API_PORT%
