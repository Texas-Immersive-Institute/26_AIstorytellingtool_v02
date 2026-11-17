@echo off
setlocal
cd /d "%~dp0"

rem Starts Takes on http://127.0.0.1:8778 and opens its window.
rem The H3 ComfyUI must already be running (127.0.0.1:8188, or the address in Settings).

where uv >nul 2>&1
if errorlevel 1 (
  echo uv was not found on PATH. Install uv from https://docs.astral.sh/uv/ and try again.
  pause
  exit /b 1
)

rem Build the UI when there is no build yet, or when any UI source is newer than it.
set "NEEDS_BUILD=0"
if not exist "apps\takes\web\dist\index.html" (
  set "NEEDS_BUILD=1"
) else (
  powershell -NoProfile -Command "$w='apps\takes\web'; $t=(Get-Item \"$w\dist\index.html\").LastWriteTime; $f=Get-ChildItem \"$w\src\",\"$w\index.html\",\"$w\package.json\",\"$w\vite.config.ts\",\"$w\tsconfig.json\" -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt $t } | Select-Object -First 1; if ($f) { exit 1 } else { exit 0 }"
  if errorlevel 1 set "NEEDS_BUILD=1"
)

if "%NEEDS_BUILD%"=="1" (
  echo Building the Takes UI...
  pushd apps\takes\web
  if not exist "node_modules\" call npm install || goto :fail
  call npm run build || goto :fail
  popd
)

uv run takestool %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%

:fail
popd
echo The UI build failed.
pause
exit /b 1
