# Takes is its own app, not a tab in the Comfy API Tool

_Partly superseded by [ADR-0006](0006-takes-talks-to-comfyui-directly.md) (2026-11-13): Takes now talks to ComfyUI directly instead of through the Comfy API Tool. That it is its own app in this repo still stands._

Takes lives in this repo as a separate app that calls the Comfy API Tool video profile (port 8766) from its own server, instead of being added as a tab inside `comfyui_apitool`. Its shots, takes and sequences are meant to feed the Story app later, so keeping them in this repo makes that merge easier. The costs: the Comfy API Tool rejects cross-origin browser calls, so Takes must call it from its server; the tool's active configuration is shared and last-write-wins, so Takes must submit one run at a time (load stage, set parameters, submit); and Takes must keep its own store for shots, takes and selections, because the tool has no favorites or tags. Scaffolding and UI pieces may be copied from `comfyui_apitool`.
