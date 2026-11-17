# Decisions

Record decisions that would otherwise be costly to rediscover. Architecture decisions live as ADRs in `docs/adr/`; this file indexes them.

- [ADR-0001](docs/adr/0001-takes-is-its-own-app.md) — Takes is its own app, not a tab in the Comfy API Tool (2026-11-11; its Comfy API Tool route superseded by ADR-0006)
- [ADR-0002](docs/adr/0002-shared-python-stack.md) — Both apps use the Comfy API Tool's stack (2026-11-11)
- [ADR-0003](docs/adr/0003-ai-through-clis-or-ollama.md) — AI runs through the Claude CLI, Codex CLI or Ollama, chosen in settings (2026-11-11)
- [ADR-0004](docs/adr/0004-extensions-are-new-shots.md) — Extensions are new shots, played from where the new part starts (2026-11-11)
- [ADR-0005](docs/adr/0005-local-embedding-matching.md) — Chat is matched with a small local embedding model, with word overlap as the floor (2026-11-11)
- [ADR-0006](docs/adr/0006-takes-talks-to-comfyui-directly.md) — Takes talks to ComfyUI directly, with its own copy of the H3 pack; ComfyUI must already be running (2026-11-13)
- Beat map (2026-11-12): the beat editor's pan/zoom is a small custom canvas (`editor/MapCanvas.tsx`, CSS transform over the normal flex layout), not React Flow. Beats and lanes keep automatic left-to-right layout with no stored positions, and form fields inside cards need no drag/wheel opt-outs. Collapsing at low zoom reflows the layout, so the canvas pins the card under the cursor across the switch.
- Takes generations (2026-11-13): a single worker runs each generation from upload through download before starting the next, rather than queueing several in ComfyUI. One GPU renders one video at a time anyway, so this makes cancelling a waiting generation free and keeps Takes from interrupting anyone else's run.
- Takes selection and upscale (2026-11-13): a shot's first finished take becomes its selected take, later takes don't replace it until chosen, and an upscaled take always becomes selected when it arrives. Upscaling a voice-reference take reuses the line already spoken (as 'your clip' audio) instead of speaking it again, so the upscale keeps the same soundtrack.
- Generated files stay out of git (2026-11-17): UI `node_modules/` and `dist/`, the Python `.venv/` and caches are listed in `.gitignore`. A new computer gets them by running `install.command` / `install.bat` once (the start launchers also rebuild a missing UI). Tracking them had put a macOS-only build binary into Windows clones and made every npm or test run show up as changes.
- Takes no-picture stages (2026-11-17): the `video_*_none` stages are built when Takes loads the pack, from the matching `*_first` stage with its frame guide taken out (`pack.without_frame_guides`), rather than shipped as recipe files. The H3 pack is copied from comfyui_apitool and isn't edited by hand, so building them keeps them in step with each re-copy; if a re-copied `*_first` recipe wires its guide differently, loading the pack fails with a clear error.
