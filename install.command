#!/bin/bash
# Installs what Story and Takes need on this Mac, then builds both UIs.
#   uv (Python and the app packages), Node.js (builds the UIs), ffmpeg (Takes).
# Node.js and ffmpeg come from Homebrew; if Homebrew is missing you are asked first.
# Double-click in Finder to run. Safe to run again: it skips what is already there.
# Quit Story and Takes before running it.

cd "$(dirname "$0")" || exit 1

# Finder-launched shells may miss user PATH entries; add the usual uv/Homebrew locations.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

pause() {
  read -r -p "Press Return to close..."
}

fail() {
  echo
  echo "Install stopped: $1"
  pause
  exit 1
}

have() {
  command -v "$1" >/dev/null 2>&1
}

ask() {
  local reply
  read -r -p "$1 [y/N] " reply
  case "$reply" in
    [Yy]*) return 0 ;;
    *) return 1 ;;
  esac
}

echo "== 1/5  uv"
if have uv; then
  echo "Found $(uv --version)."
else
  echo "Installing uv from astral.sh..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || fail "uv didn't install."
  have uv || fail "uv installed but isn't on PATH yet. Close this window and run install.command again."
fi

echo
echo "== 2/5  Node.js and ffmpeg"
missing=()
have npm || missing+=(node)
{ have ffmpeg && have ffprobe; } || missing+=(ffmpeg)
if [ ${#missing[@]} -eq 0 ]; then
  echo "Found Node.js $(node --version) and ffmpeg."
else
  echo "Missing: ${missing[*]}"
  if ! have brew; then
    echo "These are installed with Homebrew (https://brew.sh), which isn't on this Mac."
    if ask "Install Homebrew now? It asks for your Mac password."; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" ||
        fail "Homebrew didn't install."
    fi
  fi
  if have brew; then
    brew install "${missing[@]}" || fail "brew install ${missing[*]} failed."
  fi
fi
have npm || fail "Node.js is needed to build the UIs. Install it from https://nodejs.org/ and run install.command again."

echo
echo "== 3/5  Python and the app packages"
uv sync || fail "uv sync failed. If Story or Takes is running, quit it and try again."

# npm ci installs exactly what package-lock.json lists, for this computer's platform.
build_ui() {
  echo
  echo "== $1  $2 UI"
  (
    cd "apps/$3/web" || exit 1
    npm ci && npm run build
  ) || fail "The $2 UI didn't build."
}
build_ui 4/5 Story story
build_ui 5/5 Takes takes

chmod +x start-story.command start-story-lan.command start-takes.command 2>/dev/null

echo
echo "Done. Start the apps with start-story.command or start-takes.command."
if ! { have ffmpeg && have ffprobe; }; then
  echo "Note: ffmpeg is still missing. Story works without it; Takes needs it for voice reference."
  echo "      Install Homebrew (https://brew.sh), then run: brew install ffmpeg"
fi
echo "Takes also needs the H3 ComfyUI running (127.0.0.1:8188, or the address in Takes' Settings)."
echo "Story's AI lines need Ollama, the Claude CLI or the Codex CLI; choose one in Story's Settings."
pause
