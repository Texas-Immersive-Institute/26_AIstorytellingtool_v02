# Both apps use the Comfy API Tool's stack

Takes and Story both use a Python (FastAPI) server serving a React + Vite + TypeScript UI, with a shared `packages/core` (Python, plus shared TypeScript types). Takes also opens in a pywebview desktop window like the Comfy API Tool; Story is browser-only so LAN devices can join. We considered a Node/TypeScript server, which suits WebSocket chat slightly better, but chose Python so we can copy working scaffolding and UI pieces from `comfyui_apitool` and run local AI models (embeddings, Ollama clients) in-process.
