# Project: AI Storytelling Tool

## Purpose

Two local tools, built in one repo and designed to connect later:

- **Takes** (`apps/takes/`): a desktop app that sends shots straight to the H3 ComfyUI, collects the resulting takes, and plays the selected takes back to back as a sequence.
- **Story** (`apps/story/`): a teaching tool that shows how an audience-driven generative story works. You author a branching outline, run it as a playthrough with a LAN chat room, and watch in a debug view how chat is matched, weighted and remembered, and how it changes the dialogue, path and pictures.

Vocabulary for each app lives in its `CONTEXT.md`; see `CONTEXT-MAP.md`.

## Goals

**Takes v1 (built second)**
- Projects folder chosen on first start; each project is its own folder, and takes are copied into it.
- Desktop window (pywebview) over a local web app.
- Talks to ComfyUI directly with its own copy of the H3 workflow pack (ADR-0006); ComfyUI must already be running (default `127.0.0.1:8188`, address in settings).
- Shot list; drag shots to reorder the sequence.
- Generate form driven by toggles: frame mode (first / last / first+last / no picture), audio (native / your clip / voice reference), upscale on or off. One take per generation.
- Take list per shot with a player; select the take that plays.
- "Upscale this take" adds an upscaled take that becomes selected (marked with an icon).
- "Extend" creates a continuation shot (see ADR-0004).
- Back-to-back sequence playback in the app; no rendered file.
- Out of v1: 3-take seed hunts, voice-take picking, sequence export, multiple render hosts, grouping shots into scenes.

**Story v1 (built first)**
- Story projects as folders (outline, characters, assets, saved playthroughs), plus zip export.
- Scene graph (Twine-style); inside each scene, a beat editor that runs left to right, with stacked lanes and hold-over picture/audio.
- Characters with a base profile and a live profile; story variables (number, yes/no, text); story memory (AI-written, seedable, editable).
- AI lines with default lines; influence windows (optionally filling a variable); choice points with countdown, close-now and add-time.
- Matching by local embeddings; weight = match score x (1 + thumbs-ups); weight sliders in Debug.
- No-input rules: if the playthrough has had no audience input, AI lines play their default lines; a choice point that gets no messages picks at random with equal odds.
- Views: Stage (host only, visual-novel style), Chat (any LAN device, QR join, nickname), Debug and authoring (host only; includes hiding messages).
- Auto-advance with skip; playback stops at choice points.
- Saved playthroughs you can step through; an outline-only run mode.
- Beats accept pictures, video files and pre-made audio.
- AI backend chosen in settings: Claude CLI, Codex CLI or Ollama (ADR-0003). AI is used at run time only, not for authoring.
- Out of v1: simulated audience personas, chat-log replay, voices for AI lines, live picture generation, AI writing helpers.

## Constraints

- Stack: Python (FastAPI) + React/Vite/TypeScript, borrowed from `comfyui_apitool` (ADR-0002); shared code in `packages/core`.
- No hosted AI API keys for now; AI calls can take seconds, and Ollama shares the GPU with ComfyUI.
- Takes talks to ComfyUI from its server and runs one generation at a time, upload through download (ADR-0006). No Comfy API Tool service runs with it.
- Not tied to one PC: no machine-specific paths. The host computer runs the H3 ComfyUI; Takes carries the H3 workflow pack.
- Requires ffmpeg on the host (24 fps copies for extensions).

## Key locations

- `CONTEXT-MAP.md` — the two contexts and how they relate
- `apps/takes/CONTEXT.md`, `apps/story/CONTEXT.md` — glossaries
- `docs/adr/` — architecture decisions (indexed in `DECISIONS.md`)
- `packages/core/` — shared Python package `aistory_core`: app data paths, settings files, host/LAN checks, `ai.py` (Ollama / Claude CLI / Codex CLI backends), `embeddings.py` (local embedding model)
- `apps/story/src/story_app/` — Story server: `model.py` (story.json format), `checks.py`, `store.py` (project folders, playthrough files), `engine.py` (plays a story), `runner.py` (one live playthrough: ticks, AI calls, saving), `ai_writer.py` (AI prompts), `matching.py` (match scores), `api.py` (projects, settings), `live_api.py` (playthrough controls, chat, LAN join), `access.py`
- `apps/story/web/` — Story UI (React + Vite): `src/editor/` (scene graph, beat editor, panels), `src/run/` (Debug and Stage views), `src/chat/` (Chat view), `src/screens/` (stories, settings); `src/generated/story.ts` is generated from the Python model
- `apps/takes/src/takes_app/` — Takes server: `comfyui.py` (ComfyUI client and readiness check), `pack.py` (H3 pack loader, fills recipes in), `stages.py` (toggles → H3 stage, generate request, voice reference, H3 lengths), `store.py` (project folders: `project.json` with shots and takes, `media/`, `takes/`), `generator.py` (renders takes one at a time: voice step, upscale, resume after restart), `api.py` (first-start folder, projects, shots, takes), `__main__.py` (`takestool`, `takestool check`)
- `apps/takes/web/` — Takes UI (React + Vite): `src/screens/` (setup, projects, settings), `src/project/` (shot list, take list and player, generate form, media slots)
- `examples/lighthouse/` — example story using every part of the format
- `install.bat` / `install.command` — one-time setup on a new computer: installs uv, Node.js and ffmpeg if missing (winget on Windows, Homebrew on macOS, asking before installing Homebrew), runs `uv sync`, and clean-installs (`npm ci`) and builds both UIs
- `start-story.bat` — builds the UI if needed and starts Story (`start-story.command` on macOS; `-lan` variants for both)
- `start-takes.bat` / `start-takes.command` — builds the Takes UI if needed and opens Takes in its window
- `apps/takes/workflow_packs/h3_seed_hunter/` — Takes' copy of the H3 pack (recipes, `pack.json`, `PROMPTING.md`); the README names the source commit
- `../comfyui_apitool` — the Comfy API Tool, where the H3 pack and scaffolding came from (sibling repo, not part of this one; Takes doesn't call it)

## How to verify

```text
uv sync                                   # Python workspace (installs Python 3.11+ if needed)
uv run pytest -q                          # Python tests
uv run ruff check . && uv run ruff format --check .
cd apps/story/web && npm install && npm test && npm run build
npm run types                             # after changing model.py: regenerate story.ts
start-story.bat                           # run Story at http://127.0.0.1:8777 (this computer only)
start-story-lan.bat                       # same, plus the audience chat for devices on your network
uv run takestool check                    # is the H3 ComfyUI running and ready?
cd apps/takes/web && npm install && npm test && npm run build
start-takes.bat                           # Takes in its own window (server at http://127.0.0.1:8778)
uv run takestool --browser                # same, in the web browser; --no-window for the server only
```

While a Story server is running, `uv sync` (and plain `uv run`) can't replace `storytool.exe`; stop the server first, or use `uv run --no-sync`.
