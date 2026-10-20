@echo off
rem ASCII-only: Windows CMD compatibility. No PowerShell.
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto failed
set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  where py.exe >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv "%~dp0backend\.venv"
  ) else (
    where python.exe >nul 2>nul
    if errorlevel 1 goto missing
    python -m venv "%~dp0backend\.venv"
  )
  if errorlevel 1 goto failed
)
"%VENV_PY%" -m pip install -r "%~dp0backend\requirements.txt"
if errorlevel 1 goto failed
echo.
echo [Meiyuren] Python backend is ready. Start Meiyuren.cmd.
pause
exit /b 0

:missing
echo [ERROR] Python 3.11+ not found. Install Python with pip from https://python.org
goto failed

:failed
echo [ERROR] Backend setup failed. Please inspect messages above.
pause
exit /b 1
