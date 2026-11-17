@echo off
setlocal
cd /d "%~dp0"

rem Installs what Story and Takes need on this PC, then builds both UIs.
rem   uv (Python and the app packages), Node.js (builds the UIs), ffmpeg (Takes).
rem Missing tools are installed with winget, which may ask you to accept its terms.
rem Double-click to run. Safe to run again: it skips what is already there.
rem Close Story and Takes before running it, or uv can't replace their programs.

echo == 1/5  uv
call :ensure uv astral-sh.uv uv || goto :fail

echo.
echo == 2/5  Node.js and ffmpeg
call :ensure npm OpenJS.NodeJS.LTS Node.js || goto :fail
call :ensure ffprobe Gyan.FFmpeg ffmpeg

echo.
echo == 3/5  Python and the app packages
uv sync
if errorlevel 1 (
  echo uv sync failed. If Story or Takes is running, close it and try again.
  goto :fail
)

rem npm ci installs exactly what package-lock.json lists, for this computer's platform.
echo.
echo == 4/5  Story UI
call :build story || goto :fail

echo.
echo == 5/5  Takes UI
call :build takes || goto :fail

echo.
echo Done. Start the apps with start-story.bat or start-takes.bat.
where ffprobe >nul 2>&1 || echo Note: ffmpeg is still missing. Story works without it; Takes needs it for voice reference.
echo Takes also needs the H3 ComfyUI running: 127.0.0.1:8188, or the address in Takes' Settings.
echo Story's AI lines need Ollama, the Claude CLI or the Codex CLI; choose one in Story's Settings.
pause
exit /b 0

:fail
echo.
echo Install stopped.
pause
exit /b 1

rem ---------------------------------------------------------------------------
rem :ensure <command> <winget id> <name> - installs <name> with winget unless <command> is found.
:ensure
where %1 >nul 2>&1
if not errorlevel 1 (
  echo Found %~3.
  exit /b 0
)
where winget >nul 2>&1
if errorlevel 1 (
  echo %~3 is missing and winget isn't available to install it.
  echo Install winget: App Installer from the Microsoft Store, then run install.bat again.
  exit /b 1
)
echo Installing %~3 with winget...
winget install --id %2 --exact --source winget
call :refresh_path
where %1 >nul 2>&1
if not errorlevel 1 exit /b 0
echo %~3 didn't install, or isn't on PATH yet. Close this window and run install.bat again.
exit /b 1

rem Reload PATH from the registry so tools winget just installed can be found.
:refresh_path
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%p"
exit /b 0

rem :build <app> - clean install and build apps\<app>\web.
:build
pushd apps\%1\web
call npm ci
if errorlevel 1 goto :build_failed
call npm run build
if errorlevel 1 goto :build_failed
popd
exit /b 0
:build_failed
popd
echo The %1 UI didn't build.
exit /b 1
