@echo off
rem This file must stay ASCII-only with CRLF line endings (see .gitattributes):
rem cmd.exe misreads UTF-8 batch files, breaking lines apart on Cyrillic text.
rem Messages for the user are printed by scripts/start.mjs, which handles UTF-8.
setlocal EnableExtensions
chcp 65001 >nul
title Meiyuren
cd /d "%~dp0"
if errorlevel 1 goto directory_error

rem Prefer runtime\node.exe next to the project, so it can run without a system Node.
if exist "%~dp0runtime\node.exe" (
  set "NODE_BIN=%~dp0runtime\node.exe"
) else (
  where node.exe >nul 2>nul
  if errorlevel 1 goto node_missing
  set "NODE_BIN=node.exe"
)

rem Install dependencies only when they are missing.
if not exist "%~dp0node_modules\vite\package.json" (
  echo [Meiyuren] Installing dependencies, this happens once...
  where npm.cmd >nul 2>nul
  if errorlevel 1 goto npm_missing
  call npm.cmd install --no-audit --no-fund
  if errorlevel 1 goto install_error
)

echo [Meiyuren] Starting...
"%NODE_BIN%" "%~dp0scripts\start.mjs"
if errorlevel 1 goto start_error
exit /b 0

:node_missing
echo [ERROR] Node.js not found. Install Node.js 20+ from https://nodejs.org
echo         or put node.exe into the runtime folder.
goto failed

:npm_missing
echo [ERROR] Dependencies are not installed and npm was not found.
echo         Install Node.js with npm, or copy the node_modules folder here.
goto failed

:directory_error
echo [ERROR] Cannot open the Meiyuren folder.
goto failed

:install_error
echo [ERROR] npm install failed. Check your internet connection.
goto failed

:start_error
echo [ERROR] The server stopped with an error, see the messages above.
goto failed

:failed
echo.
pause
exit /b 1
