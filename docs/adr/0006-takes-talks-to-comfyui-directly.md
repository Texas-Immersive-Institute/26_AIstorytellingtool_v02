# Takes talks to ComfyUI directly, with its own copy of the H3 pack

_2026-11-13. Supersedes the part of [ADR-0001](0001-takes-is-its-own-app.md) that had Takes call the Comfy API Tool video profile._

Takes sends work straight to the H3 ComfyUI over ComfyUI's own HTTP API (`/upload/image`, `/prompt`, `/history`, `/queue`, `/interrupt`, `/view`). No Comfy API Tool service runs alongside it: the user wants Takes to stand on its own. Takes carries a copy of the H3 Seed Hunter workflow pack (`apps/takes/workflow_packs/h3_seed_hunter`, recipes plus `pack.json`) and fills recipes in itself, reproducing the Comfy API Tool's rules so the same pack behaves the same way: pack defaults from the recipe, locked inputs, `{run_id}` in output names, reference media as the `MiniMaxH3MediaLoader` media state, LoRAs as Pixaroma state. Takes expects ComfyUI to be running already (`http://127.0.0.1:8188`, or the address in settings) and tells the user to start it if not; it never launches ComfyUI. It recognises the H3 ComfyUI by the `H3PromptIDE` node.

Generations still run one at a time, each from upload through download, so ComfyUI's queue holds at most one Takes run and cancelling a waiting generation costs nothing. Takes only interrupts ComfyUI when its own run is the one rendering.

Costs: the pack is now copied in two repos, so a pack change in `comfyui_apitool` must be copied over by hand (the pack README records the source commit). Takes owns the filling rules too, and they must follow the pack format if it changes. Progress within a run isn't shown yet (that needs ComfyUI's websocket); a generation shows queued, preparing, rendering, downloading, done.
