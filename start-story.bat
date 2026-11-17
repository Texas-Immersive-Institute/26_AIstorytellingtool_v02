@echo off
setlocal
cd /d "%~dp0"

rem Starts Story on http://127.0.0.1:8777 and opens it in your browser.
rem Pass --lan to let audience devices on your network open the chat.

where uv >nul 2>&1
if errorlevel 1 (
  echo uv was not found on PATH. Install uv from https://docs.astral.sh/uv/ and try again.
  pause
  exit /b 1
)

rem Build the UI when there is no build yet, or when any UI source is newer than it.
set "NEEDS_BUILD=0"
if not exist "apps\story\web\dist\index.html" (
  set "NEEDS_BUILD=1"
) else (
  powershell -NoProfile -Command "$w='apps\story\web'; $t=(Get-Item \"$w\dist\index.html\").LastWriteTime; $f=Get-ChildItem \"$w\src\",\"$w\index.html\",\"$w\package.json\",\"$w\vite.config.ts\",\"$w\tsconfig.json\" -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt $t } | Select-Object -First 1; if ($f) { exit 1 } else { exit 0 }"
  if errorlevel 1 set "NEEDS_BUILD=1"
)

if "%NEEDS_BUILD%"=="1" (
  echo Building the Story UI...
  pushd apps\story\web
  if not exist "node_modules\" call npm install || goto :fail
  call npm run build || goto :fail
  popd
)

uv run storytool %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%

:fail
popd
echo The UI build failed.
pause
exit /b 1
