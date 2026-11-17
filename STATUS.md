# Status

_Last updated: 2026-11-17 by Claude Code_

## Current focus

Story v1 milestones 1 to 6 are built: authoring, playthroughs, matching, AI backends, and the Stage, Chat and Debug views. Left for v1: milestone 7 (step through saved playthroughs, polish).

Takes has started (2026-11-13, user's call to begin it now): Takes talks to the H3 ComfyUI directly with its own copy of the H3 pack (user decision, ADR-0006). The connection, projects/shots/takes, the Takes UI and `start-takes.command` / `.bat` are built. Left: progress while rendering, extend, sequence playback.

## Done

- [x] Design settled through a grilling session: glossaries, ADRs, v1 scope in `PROJECT.md`
- [x] Build order changed to Story first, Takes second (user decision, 2026-11-11)
- [x] Milestone 1, foundation: workspace, story.json format with checks, project folders, host-only API, first-start setup, example story.
- [x] Milestone 2, authoring: scene graph, beat editor with lanes and holds, panels, autosave; direct upload into a beat's picture/audio slot (drop or Upload…); scene boxes show their picture.
- [x] Milestone 3, playthrough engine and runner, saved playthroughs, outline-only mode.
- [x] Milestone 4, matching: `EmbeddingMatcher` (fastembed, `BAAI/bge-small-en-v1.5`, CPU) behind the `Matcher` interface, max'd with word overlap; download from Settings; falls back to word overlap until downloaded (ADR-0005).
- [x] Milestone 5, AI: `aistory_core.ai` backends for Ollama, Claude CLI and Codex CLI with sign-in-aware readiness checks and `auto` choice (ADR-0003 amended); the engine asks for AI lines and variable fills as async requests with timeouts and falls back to defaults; AI answers also add story memory notes and live-profile notes; Settings screen with readiness, test call and timeout.
- [x] Milestone 6, views: Stage view (`#/stage`, full screen with F, QR and join link when on the LAN), Chat view (`#/chat`, name, tap-to-choose options, thumbs-ups, per-device rate limit), Debug view (AI status, weighting sliders, live profiles, AI calls in the event log). `start-story-lan.bat`.
- [x] Beat map (2026-11-12): the scene's beats sit on a pan/zoom map (scroll to zoom at the cursor, drag empty space or middle-drag to move, Fit, 100%). Cards collapse to large-type summaries below 55% zoom and expand above 65%; the card under the cursor stays put, and clicking a collapsed card zooms in on it. A split's lanes branch out stacked beside the split card and rejoin before the next step. Draggable pane edges (sidebar, graph/beat map, Debug view's operator column), remembered per computer; double-click an edge to reset. Checked in the browser on the Lighthouse example.
- [x] Takes milestone 1, ComfyUI connection (2026-11-13): `apps/takes` server (`takestool`, port 8778) with its own copy of the H3 pack (from comfyui_apitool `addce38`). `pack.py` fills recipes in the way the Comfy API Tool does (defaults, locked inputs, `{run_id}` output folders, media-loader references, LoRAs). `comfyui.py` uploads references, queues the workflow, waits on history, cancels (interrupts only its own run) and downloads outputs; `takestool check` / `GET /api/comfyui` say whether the H3 ComfyUI (found by its `H3PromptIDE` node) is ready, at 127.0.0.1:8188 or the address in settings. Frame / audio (native or your clip) / upscale toggles map to the H3 stage; a seed is picked and recorded when none is given. Generations run one at a time and copy their files into Takes' data folder. 22 Takes tests against a stand-in ComfyUI; 100 Python tests and ruff pass. Real run 2026-11-13 on this computer (ComfyUI 0.42.5, RTX 3080 Ti): a 1-take native first-frame generation through Takes' API queued without node errors, rendered in 110 s and downloaded `final_00001-audio.mp4` (480×864, 24 fps, 124 frames = 5.17 s, AAC audio) that follows the prompt.
- [x] Takes milestone 2, projects / shots / takes / voice reference / upscale this take (2026-11-13), server and API (no screens yet): projects folder chosen on first start (`PUT /api/settings`, suggests Documents/AI Takes Projects); each project is a folder with `project.json`, `media/` and `takes/<take id>/`. Shots: add (or insert after), rename, notes, reorder (full id list, for drag), delete. Takes per shot: generate, choose the take that plays (first finished take is chosen automatically), cancel, delete (falls back to the newest finished take), play. Voice reference: `voice_takes` speaks the line in the recorded voice, take 1 is kept in the project and forced in as <Audio 1>, and the video length comes from it (ffprobe, rounded up to an H3 length). Upscale this take: same request and seed on the upscale stage (a voice take reuses its spoken line), and the upscaled take becomes the chosen one. Takes waiting or rendering when Takes closed are picked up on the next start without re-queueing. 106 Python tests and ruff pass. Real renders on this computer (RTX 3080 Ti): voice-reference take in 195 s (line 5.18 s → video 5.17 s, voice confirmed in the soundtrack), native take in 85 s, its upscale in 155 s (1088×1952, 48 fps, same take as the source, then chosen automatically).
- [x] Takes UI and launchers (2026-11-14): `apps/takes/web` (React + Vite, Story's look). Projects screen, first-start folder, Settings (projects folder, ComfyUI address, readiness). Project screen: shot list with drag to reorder, add / insert after / rename / notes / delete; a player for the selected take (or any take you watch) and the take list (status and elapsed time, ★ select, ⬆ upscale this take, cancel, delete, reuse settings); a generate form with frame / audio / upscale toggles, drop-or-click picture and audio slots, voice reference (recording, line, tone, length estimate), length, size, seed. The form remembers what you typed per shot and starts from the shot's newest take; the screen refreshes every 2 s while anything renders. `takestool` now serves the built UI and opens it in a pywebview window (`--browser` for the web browser, `--no-window` for the server only; falls back to the browser if no window can open; a second start opens another window on the running server). `start-takes.command` / `start-takes.bat` build the UI when its source changed, then run `takestool`. Checked on this Mac with a throwaway project (ComfyUI not running): screens, select, add shot, drag-reorder (saved), picture upload, a generate that fails cleanly with "ComfyUI isn't running"; `start-takes.command` rebuilt the UI and opened the native window. 107 Python tests, ruff, 3 web tests and the build pass.
- [x] Verified 2026-11-11: 78 Python tests, 11 web tests, type-check and build pass. In the browser: Settings, a phone-sized Chat sending a message, the Debug view, the Stage view, and a live playthrough where Codex picked "Sir Barksalot" from chat in 7.3 s and wrote Mara's line in 13.5 s.
- [x] Installers (2026-11-17): `install.command` (macOS) and `install.bat` (Windows) install uv, Node.js and ffmpeg when missing, run `uv sync`, then `npm ci` and build both UIs; safe to run again. `install.command` was run on this Mac (uv and Node present, no Homebrew, Homebrew declined): it synced, built both UIs and reported ffmpeg as missing. `install.bat` has not been run on Windows yet.
- [x] Stopped tracking generated files (2026-11-17, user decision): `.gitignore` added; `node_modules/`, `dist/` and `__pycache__/` removed from git (about 7,750 files, still on disk). The tracked `node_modules` held the macOS-only `@rolldown/binding-darwin-arm64`, which broke UI builds on a Windows clone. Not committed yet.

- [x] Python pinned to 3.14 with `.python-version` (2026-11-17): on a Windows PC `uv sync` picked Python 3.15, which onnxruntime 1.31.1 (needed by fastembed) has no packages for. Reproduced here with 3.15 and checked that `uv sync` replaces a 3.15 `.venv` with 3.14 once the pin is in place. Move the pin up when onnxruntime publishes 3.15 packages.

- [x] Takes: no-picture takes (2026-11-17): a 'No picture' frame mode runs on the prompt alone (H3's T2VA format: no picture line, start with `integrated_multimodal_description:`). `Pack` builds `video_{1take,3takes,upscale}_{native,audio}_none` from each `*_first` stage by taking out the frame guide (`MiniMaxH3AddGuide`) and the picture resize that fed it; the pack files are unchanged. Works with native, your clip and voice reference audio, and with upscale this take. Also fixed the shot pane growing past the window under 1150 px when a take's prompt has a long word. 109 Python tests, ruff, 3 web tests and the build pass; in the browser a no-picture take was accepted as `video_1take_native_none` and failed cleanly because ComfyUI wasn't running. Not yet rendered by the real H3 ComfyUI.

## Next

- [ ] Takes: show progress while rendering (ComfyUI websocket)
- [ ] Takes: extend as continuation shots (ADR-0004: in-point on the low-res take, 24 fps ffmpeg copy of an upscaled source)
- [ ] Takes: back-to-back sequence playback
- [ ] Run `install.bat` on the Windows PC (winget installs, PATH refresh, both UI builds)
- [ ] Takes: render a no-picture take on the real H3 ComfyUI and check the prompt alone sets the scene (the Ref2VA model and the T2VA prompt format are the ones the extend stages already use)
- [ ] Takes: try the UI against the real H3 ComfyUI on the Windows PC (generate, voice reference, upscale) via `start-takes.bat`

- [ ] 7. Step through a saved playthrough in the Debug view; polish
- [ ] Try it with real devices: run `start-story-lan.bat`, allow the firewall prompt on private networks, scan the QR code from a phone
- [ ] Download the matching model from Settings and tune `SEMANTIC_LOW`/`SEMANTIC_HIGH` in `matching.py` against real chat
- [ ] Optional: install Ollama and `ollama pull llama3.2:3b` for a free local backend; or run `claude auth login` to use the Claude CLI

## Risks / blockers

- Takes has rendered `voice_takes`, `video_1take_native_first`, `video_1take_audio_first` and `video_upscale_native_first` for real. The last-frame, first+last and audio-upscale stages are only tested against the stand-in; several are marked "not run yet" in the pack itself (audio upscale: check the audio survives).
- Voice reference uses spoken take 1 of 3 (voice-take picking is out of v1); a weak take 1 means re-generating the take.
- The H3 pack now lives in two repos; a change in comfyui_apitool must be copied over by hand.

- Beat map: trackpad two-finger scroll zooms rather than pans (map style). Cards themselves are fixed width; only panes resize.

- Not exercised here: Ollama (not installed), the Claude CLI (installed but not signed in), the embedding model (not downloaded), LAN access from a real second device. Each has tests with fakes; the real paths still need a first run.
- AI lines through Codex take about 7–14 s, so the stage waits ("…") on each AI line while chat is active. Shorter intents, fewer AI lines, or a local model help.
- Embedding score bounds are untuned guesses; use the Debug view's threshold slider until they are tuned.
- Beat timing ignores audio length (reading time only).
- While a Story server is running, `uv sync` can't replace `storytool.exe`. Stop the server first. The server that was running at 7:06 PM predates these changes and needs a restart.
- Takes UI not yet exercised against a real render, on Windows, or in the window with a mouse (drag-reorder was checked with synthetic drag events in the browser; closing the window should stop the server, unchecked). pywebview on Windows needs the WebView2 runtime (built into Windows 11); without it Takes opens in the browser.
- Takes: upscaled extensions vs. low-res preview with the same seed is unverified; several H3 pack stages are marked "not run yet".
