@echo off
rem ASCII-only with CRLF line endings: cmd.exe misreads UTF-8 batch files.
setlocal EnableExtensions
cd /d "%~dp0"
echo [Meiyuren] Creating a desktop shortcut...
cscript.exe //nologo "%~dp0scripts\create-shortcut.vbs"
if errorlevel 1 (
  echo [ERROR] Could not create the shortcut.
) else (
  echo [Meiyuren] Done. Start Meiyuren from the desktop icon.
)
echo.
pause
