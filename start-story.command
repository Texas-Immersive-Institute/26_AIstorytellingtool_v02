#!/bin/bash
# Starts Story on http://127.0.0.1:8777 and opens it in your browser.
# Pass --lan to let audience devices on your network open the chat.
# Double-click in Finder to run.

cd "$(dirname "$0")" || exit 1

# Finder-launched shells may miss user PATH entries; add the usual uv/npm locations.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

pause() {
  read -r -p "Press Return to close..."
}

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was not found on PATH. Install uv from https://docs.astral.sh/uv/ and try again."
  pause
  exit 1
fi

# Build the UI when there is no build yet, or when any UI source is newer than it.
web="apps/story/web"
needs_build=0
if [ ! -f "$web/dist/index.html" ]; then
  needs_build=1
elif [ -n "$(find "$web/src" "$web/index.html" "$web/package.json" "$web/vite.config.ts" "$web/tsconfig.json" \
    -newer "$web/dist/index.html" -type f -print -quit 2>/dev/null)" ]; then
  needs_build=1
fi

if [ $needs_build -eq 1 ]; then
  echo "Building the Story UI..."
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm was not found on PATH. Install Node.js from https://nodejs.org/ and try again."
    pause
    exit 1
  fi
  (
    cd apps/story/web || exit 1
    if [ ! -d "node_modules" ]; then
      npm install || exit 1
    fi
    npm run build
  ) || {
    echo "The UI build failed."
    pause
    exit 1
  }
fi

uv run storytool "$@"
status=$?
if [ $status -ne 0 ]; then
  pause
fi
exit $status
