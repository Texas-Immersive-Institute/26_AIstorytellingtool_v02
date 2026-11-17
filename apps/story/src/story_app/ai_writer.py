"""Prompts for the AI's two jobs during a playthrough, and the call that runs them.

1. line: write one AI line in character, from its intent, the story so far and what the
   audience said. It may also return up to two story memory notes and one live-profile note,
   so memory grows without extra AI calls.
2. fill: pick a story variable's value out of an influence window's top messages.

The engine builds the context (engine._story_context); this module only turns it into text
and parses the JSON answer. Any failure becomes {"error": ...}, and the engine falls back.
"""

from __future__ import annotations

import json
from typing import Any

from aistory_core.ai import AiError, Backend, ask_json

from story_app.engine import AiRequest

SYSTEM_LINE = """You write dialogue for a live, audience-driven story shown on a big screen.
Write exactly one line for the speaking character: in character, in their speaking style,
doing what the intent asks, and reacting to the audience's messages when they fit the moment.
Keep it under 30 words. No stage directions, no quotation marks, no narration about the audience.
Respect story variables and memory as established facts.
Answer with JSON only:
{"line": "<the line>", "memory": ["<0-2 new facts worth remembering later, e.g. a running joke or established backstory>"], "profile": ["<0-1 new note about the speaker, e.g. how they now feel about someone>"]}
Leave memory and profile empty unless something genuinely new was established."""

SYSTEM_FILL = """You read an audience's chat messages for a live story and pick one value for a story variable.
Use the highest-weighted messages, prefer what most of the audience agrees on, keep it short
(a name or a few words), and ignore anything offensive. If nothing fits, use null.
Answer with JSON only: {"value": <the value, or null>, "memory": ["<0-1 fact worth remembering>"]}"""


def build_prompt(req: AiRequest) -> tuple[str, str]:
    ctx = req.context
    parts = [f"STORY: {ctx['story']['title']} - {ctx['story']['description']}"]
    if ctx.get("scene"):
        parts.append(f"SCENE: {ctx['scene']['title']} - {ctx['scene']['summary']}")
    for c in ctx.get("characters", []):
        profile = "; ".join(f"{k}: {v}" for k, v in c["profile"].items() if v)
        live = " | ".join(c["live_profile"])
        parts.append(
            f"CHARACTER {c['name']}{' (speaking)' if c['speaking'] else ''}: {profile}"
            + (f" | since the story began: {live}" if live else "")
        )
    if ctx.get("variables"):
        parts.append(
            "STORY VARIABLES: " + json.dumps({v["name"]: v["value"] for v in ctx["variables"]})
        )
    if ctx.get("memory"):
        parts.append("STORY MEMORY:\n- " + "\n- ".join(ctx["memory"]))
    if ctx.get("recent_lines"):
        parts.append(
            "RECENT LINES:\n"
            + "\n".join(f"{line['speaker']}: {line['text']}" for line in ctx["recent_lines"])
        )

    if req.kind == "line":
        parts.append(f"SPEAKER: {ctx['speaker']}")
        parts.append(f"INTENT: {ctx['intent'] or 'continue the scene naturally'}")
        parts.append(f"THE AUTHOR'S DEFAULT LINE (for tone; do not copy it): {ctx['default_line']}")
        if ctx.get("action"):
            parts.append(f"ACTION: {ctx['action']}")
        audience = ctx.get("audience") or []
        parts.append(
            "AUDIENCE SAID:\n- " + "\n- ".join(audience)
            if audience
            else "AUDIENCE SAID: nothing new"
        )
        return SYSTEM_LINE, "\n\n".join(parts)

    var = ctx["variable"]
    parts.append(f"VARIABLE: {var['name']} ({var['type']}) - {var['description']}")
    parts.append(f"THE AUDIENCE WAS ASKED: {ctx['question']}")
    parts.append(
        "TOP MESSAGES (weight, text):\n"
        + "\n".join(f"{m['weight']}: {m['text']}" for m in ctx["messages"])
    )
    return SYSTEM_FILL, "\n\n".join(parts)


async def run_request(backend: Backend, req: AiRequest, timeout: float) -> dict[str, Any]:
    """Answer an engine AiRequest. Never raises: errors come back as {"error": ...}."""
    system, prompt = build_prompt(req)
    try:
        answer, seconds = await ask_json(backend, system, prompt, timeout)
    except AiError as exc:
        return {"error": str(exc), "backend": backend.label}
    except Exception as exc:  # a backend bug must not stall the playthrough
        return {"error": f"{type(exc).__name__}: {exc}", "backend": backend.label}
    return {**answer, "backend": backend.label, "seconds": round(seconds, 2)}
