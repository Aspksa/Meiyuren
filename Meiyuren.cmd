@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Meiyuren - локальный веб-аватар
cd /d "%~dp0"
if errorlevel 1 goto directory_error

rem Если рядом лежит runtime\node.exe, используем его вместо системного Node.
if exist "%~dp0runtime\node.exe" (
  set "NODE_BIN=%~dp0runtime\node.exe"
) else (
  where node.exe >nul 2>nul
  if errorlevel 1 goto node_missing
  set "NODE_BIN=node.exe"
)

rem Проверяем зависимости относительно папки проекта, а не буквы диска.
if not exist "%~dp0node_modules\vite\package.json" (
  echo [Meiyuren] Зависимости не найдены. Устанавливаю...
  where npm.cmd >nul 2>nul
  if errorlevel 1 goto npm_missing
  call npm.cmd install --no-audit --no-fund
  if errorlevel 1 goto install_error
)

echo [Meiyuren] Запускаю приложение...
"%NODE_BIN%" "%~dp0scripts\start.mjs"
if errorlevel 1 goto start_error
exit /b 0

:node_missing
echo [ОШИБКА] Не найден Node.js. Установите Node.js 20+.
echo Для запуска без системного Node положите node.exe в папку runtime.
goto failed

:npm_missing
echo [ОШИБКА] Пакеты не установлены, а npm не найден.
echo Установите Node.js с npm или заранее перенесите папку node_modules.
goto failed

:directory_error
echo [ОШИБКА] Не удалось открыть папку Meiyuren.
goto failed

:install_error
echo [ОШИБКА] Не удалось установить зависимости. Проверьте подключение к интернету.
goto failed

:start_error
echo [ОШИБКА] Сервер завершился с ошибкой.
goto failed

:failed
echo.
pause
exit /b 1
