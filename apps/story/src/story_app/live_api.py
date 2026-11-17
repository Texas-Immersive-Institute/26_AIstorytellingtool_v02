"""Live endpoints: the running playthrough (host only), the audience chat (any LAN device),
and the join link and QR code shown on the Stage.

Handlers that touch the engine are async so they run on the event loop thread, one at a time,
alongside the runner's ticks (see runner.py).
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import socket
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal

import segno
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from story_app.engine import Engine
from story_app.runner import RunManager

CHAT_MESSAGE_MAX = 280
CHAT_MIN_GAP_S = 0.4  # spam is allowed, but not faster than this per device
CHAT_RECENT = 40
PARTICIPANT = re.compile(r"[A-Za-z0-9_-]{6,40}")


class Control(BaseModel):
    action: Literal["pause", "resume", "skip", "close_window", "add_time", "force_option", "tune"]
    seconds: float = 15
    option_id: str | None = None
    thumbs_up_factor: float | None = Field(default=None, ge=0, le=10)
    match_threshold: float | None = Field(default=None, ge=0, le=1)


class SendMessage(BaseModel):
    author: str
    text: str


class Voter(BaseModel):
    voter: str


class Hidden(BaseModel):
    hidden: bool = True


class NewMemory(BaseModel):
    text: str
    about: str | None = None


class EditMemory(BaseModel):
    text: str | None = None
    pinned: bool | None = None


class ChatMessage(BaseModel):
    participant: str
    name: str = Field(min_length=1, max_length=24)
    text: str = Field(min_length=1, max_length=CHAT_MESSAGE_MAX)


class ChatThumbs(BaseModel):
    participant: str


def lan_addresses() -> list[str]:
    """This computer's private IPv4 addresses, best guess first."""
    found: list[str] = []
    try:  # the address used for outbound traffic (no packet is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(str(info[4][0]))
    except OSError:
        pass
    private = [
        a
        for a in dict.fromkeys(found)
        if a.startswith(("192.168.", "10.")) or re.match(r"172\.(1[6-9]|2\d|3[01])\.", a)
    ]
    return private


def chat_view(snap: dict[str, Any]) -> dict[str, Any]:
    """What audience devices may see: no scores, weights, variables, memory or AI details."""
    base = {
        "active": snap.get("active", False),
        "epoch": snap.get("epoch"),
        "version": snap.get("version"),
    }
    if not snap.get("active"):
        return base
    win = snap.get("window")
    wait = snap.get("wait") or {}
    line = snap.get("line")
    return {
        **base,
        "title": snap.get("title"),
        "status": snap.get("status"),
        "scene_title": (snap.get("scene") or {}).get("title"),
        "line": {"speaker_name": line.get("speaker_name"), "text": line.get("text")}
        if line
        else None,
        "window": None
        if not win
        else {
            "id": win["id"],
            "kind": win["kind"],
            "prompt": win["prompt"],
            "options": [{"id": o["id"], "label": o["label"]} for o in win.get("options") or []],
            "remaining": wait.get("remaining"),
        },
        "messages": [
            {
                "id": m["id"],
                "author": m["author"],
                "author_id": m.get("author_id"),
                "text": m["text"],
                "thumbs": m["thumbs"],
            }
            for m in (snap.get("messages") or [])
            if not m["hidden"]
        ][-CHAT_RECENT:],
    }


def sse(
    request: Request, runs: RunManager, view: Callable[[dict[str, Any]], dict[str, Any]]
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        seen = -1
        while not await request.is_disconnected():
            if runs.version != seen:
                seen = runs.version
                yield f"data: {json.dumps(view(runs.snapshot()))}\n\n"
            try:
                await asyncio.wait_for(runs.wait_change(seen), timeout=10)
            except TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


def live_router(runs: RunManager, *, lan: bool, port: Callable[[], int]) -> APIRouter:
    api = APIRouter(prefix="/api/v1")
    last_chat: dict[str, float] = {}

    # --- operator (host only; see access.py) ---------------------------------------

    @api.get("/run")
    async def run_snapshot() -> dict[str, Any]:
        return runs.snapshot()

    @api.get("/run/stream")
    async def run_stream(request: Request) -> StreamingResponse:
        return sse(request, runs, lambda s: s)

    @api.post("/run/control")
    async def run_control(body: Control) -> dict[str, Any]:
        def do(engine: Engine, now: float) -> bool:
            match body.action:
                case "pause":
                    return engine.pause(now)
                case "resume":
                    return engine.resume(now)
                case "skip":
                    return engine.skip(now)
                case "close_window":
                    return engine.close_window(now)
                case "add_time":
                    return engine.add_time(now, body.seconds)
                case "force_option":
                    return engine.force_option(now, body.option_id or "")
                case "tune":
                    values = {
                        k: v
                        for k, v in (
                            ("thumbs_up_factor", body.thumbs_up_factor),
                            ("match_threshold", body.match_threshold),
                        )
                        if v is not None
                    }
                    return engine.tune(now, **values)
            return False

        return {"ok": runs.act(do), **runs.snapshot()}

    @api.post("/run/stop")
    async def run_stop() -> dict[str, Any]:
        await runs.stop()
        return runs.snapshot()

    @api.post("/run/messages", status_code=201)
    async def run_message(body: SendMessage) -> dict[str, Any]:
        msg = runs.act(
            lambda e, now: e.add_message(now, body.author, body.text, from_operator=True)
        )
        if msg is None:
            raise HTTPException(400, "Empty message, or the playthrough has ended.")
        return msg.public()

    @api.post("/run/messages/{message_id}/thumbs")
    async def run_thumbs(message_id: str, body: Voter) -> dict[str, bool]:
        return {"ok": runs.act(lambda e, now: e.thumbs_up(now, message_id, body.voter))}

    @api.post("/run/messages/{message_id}/hidden")
    async def run_hide(message_id: str, body: Hidden) -> dict[str, bool]:
        return {"ok": runs.act(lambda e, now: e.hide_message(now, message_id, body.hidden))}

    @api.post("/run/memory", status_code=201)
    async def run_add_memory(body: NewMemory) -> dict[str, Any]:
        entry = runs.act(lambda e, now: e.add_memory(now, body.text, body.about))
        if entry is None:
            raise HTTPException(400, "Write something first.")
        return entry.public()

    @api.patch("/run/memory/{entry_id}")
    async def run_edit_memory(entry_id: str, body: EditMemory) -> dict[str, bool]:
        return {
            "ok": runs.act(
                lambda e, now: e.edit_memory(now, entry_id, text=body.text, pinned=body.pinned)
            )
        }

    @api.delete("/run/memory/{entry_id}")
    async def run_delete_memory(entry_id: str) -> dict[str, bool]:
        return {"ok": runs.act(lambda e, now: e.delete_memory(now, entry_id))}

    # --- joining from the LAN -------------------------------------------------------

    def chat_urls() -> list[str]:
        return [f"http://{ip}:{port()}/#/chat" for ip in lan_addresses()]

    @api.get("/lan")
    async def lan_info() -> dict[str, Any]:
        urls = chat_urls() if lan else []
        return {
            "listening": lan,
            "urls": urls,
            "hint": None
            if lan
            else "Start Story with start-story-lan.bat (or `storytool --lan`) so phones on your network can join the chat.",
        }

    @api.get("/lan/qr.svg")
    async def lan_qr() -> Response:
        urls = chat_urls() if lan else []
        if not urls:
            raise HTTPException(404, "Story is not listening on the LAN.")
        buf = io.BytesIO()
        segno.make(urls[0], error="m").save(
            buf, kind="svg", scale=8, border=2, dark="#111111", light="#ffffff"
        )
        return Response(buf.getvalue(), media_type="image/svg+xml")

    # --- audience chat (any LAN device) ----------------------------------------------

    @api.get("/chat/state")
    async def chat_state() -> dict[str, Any]:
        return chat_view(runs.snapshot())

    @api.get("/chat/stream")
    async def chat_stream(request: Request) -> StreamingResponse:
        return sse(request, runs, chat_view)

    @api.post("/chat/messages", status_code=201)
    async def chat_send(body: ChatMessage) -> dict[str, Any]:
        if not PARTICIPANT.fullmatch(body.participant):
            raise HTTPException(400, "Reload the chat page and try again.")
        now = time.monotonic()
        if now - last_chat.get(body.participant, 0.0) < CHAT_MIN_GAP_S:
            raise HTTPException(429, "Slow down a little.")
        last_chat[body.participant] = now
        msg = runs.act(
            lambda e, t: e.add_message(t, body.name, body.text, author_id=body.participant)
        )
        if msg is None:
            raise HTTPException(409, "The story isn't taking messages right now.")
        return {"id": msg.id}

    @api.post("/chat/messages/{message_id}/thumbs")
    async def chat_thumbs(message_id: str, body: ChatThumbs) -> dict[str, bool]:
        if not PARTICIPANT.fullmatch(body.participant):
            raise HTTPException(400, "Reload the chat page and try again.")
        return {"ok": runs.act(lambda e, now: e.thumbs_up(now, message_id, body.participant))}

    return api
