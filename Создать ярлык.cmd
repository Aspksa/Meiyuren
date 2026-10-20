@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
echo [Meiyuren] Создаю ярлык на рабочем столе...
cscript.exe //nologo "%~dp0scripts\create-shortcut.vbs"
if errorlevel 1 (
  echo [ОШИБКА] Не удалось создать ярлык.
) else (
  echo [Meiyuren] Ярлык готов. Запускайте через значок на рабочем столе.
)
echo.
pause
