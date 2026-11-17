"""Runs one playthrough at a time on the host: ticks the engine, answers its AI requests in the
background, saves it, and tells listeners (Stage, Chat, Debug) when anything changes.

Everything that touches the engine runs on the event loop thread, so the engine never sees
two callers at once (API handlers that use it are async for this reason).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aistory_core.ai import Backend

from story_app.ai_writer import run_request
from story_app.engine import Engine, Mode
from story_app.matching import LexicalMatcher, Matcher
from story_app.store import ProjectStore

TICK_S = 0.1
SAVE_EVERY_S = 2.0

# (backend or None, sentence saying why) for the current AI settings
ChooseBackend = Callable[[], Awaitable[tuple[Backend | None, str]]]


class RunError(Exception):
    pass


async def _no_ai() -> tuple[Backend | None, str]:
    return None, "AI is not configured."


class RunManager:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        choose_backend: ChooseBackend = _no_ai,
        make_matcher: Callable[[], Matcher] = LexicalMatcher,
        ai_timeout: Callable[[], float] = lambda: 30.0,
    ):
        self.clock = clock
        self.choose_backend = choose_backend
        self.make_matcher = make_matcher
        self.ai_timeout = ai_timeout
        self.engine: Engine | None = None
        self.backend: Backend | None = None
        self.ai_reason = ""
        self.store: ProjectStore | None = None
        self.slug: str | None = None
        self.playthrough_id: str | None = None
        self.version = 0
        self.epoch = time.time_ns()  # lets clients tell a server restart from a stale update
        self._event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._ai_tasks: dict[str, asyncio.Task[None]] = {}
        self._dirty = False
        self._saved_at = 0.0

    # --- lifecycle -------------------------------------------------------------------

    async def start(self, store: ProjectStore, slug: str, mode: Mode) -> dict[str, Any]:
        await self.stop()
        story = store.load(slug)
        self.store, self.slug = store, slug
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        pid, n = base, 2
        while store.has_playthrough(slug, pid):
            pid, n = f"{base}-{n}", n + 1
        self.playthrough_id = pid
        if mode == "live":
            self.backend, self.ai_reason = await self.choose_backend()
        else:
            self.backend, self.ai_reason = None, "Outline-only playthrough: AI is off."
        timeout = self.ai_timeout()
        matcher = await asyncio.to_thread(self.make_matcher)  # may load a model from disk
        self.engine = Engine(
            story,
            now=self.clock(),
            mode=mode,
            matcher=matcher,
            ai_timeout=timeout if self.backend else None,
            ai_label=self.backend.label if self.backend else None,
        )
        self._dirty = True
        self._save(force=True)
        self._changed()
        self._task = asyncio.create_task(self._loop())
        self._dispatch_ai()
        return self.snapshot()

    async def stop(self) -> None:
        for task in self._ai_tasks.values():
            task.cancel()
        self._ai_tasks.clear()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self.engine:
            self.engine.stop(self.clock())
            self._dirty = True
            self._save(force=True)
            self._changed()

    async def _loop(self) -> None:
        while self.engine and not self.engine.ended:
            await asyncio.sleep(TICK_S)
            if self.engine.tick(self.clock()):
                self._dirty = True
                self._changed()
            self._dispatch_ai()
            self._save()
        self._save(force=True)

    # --- AI ---------------------------------------------------------------------------

    def _dispatch_ai(self) -> None:
        """Start the backend call for the engine's pending AI request, once."""
        engine, backend = self.engine, self.backend
        req = engine.pending_ai if engine else None
        if not engine or not req or not backend or req.id in self._ai_tasks:
            return
        self._ai_tasks = {k: t for k, t in self._ai_tasks.items() if not t.done()}

        async def work() -> None:
            result = await run_request(backend, req, self.ai_timeout())
            if self.engine is engine and engine.resolve_ai(self.clock(), req.id, result):
                self._dirty = True
                self._changed()
                self._dispatch_ai()  # the next line may need the AI right away

        self._ai_tasks[req.id] = asyncio.create_task(work())

    # --- controls ---------------------------------------------------------------------

    def act(self, fn: Callable[[Engine, float], Any]) -> Any:
        """Run one engine control and publish the change."""
        if not self.engine:
            raise RunError("No playthrough is running.")
        result = fn(self.engine, self.clock())
        self._dirty = True
        self._changed()
        self._dispatch_ai()
        if self.engine.ended:
            self._save(force=True)
        return result

    def snapshot(self) -> dict[str, Any]:
        if not self.engine:
            return {"active": False, "version": self.version, "epoch": self.epoch}
        snap = self.engine.snapshot(self.clock())
        snap["ai"]["reason"] = self.ai_reason
        return {
            "active": True,
            "version": self.version,
            "epoch": self.epoch,
            "slug": self.slug,
            "playthrough_id": self.playthrough_id,
            **snap,
        }

    async def wait_change(self, version: int) -> None:
        while self.version == version:
            await self._event.wait()

    # --- helpers ----------------------------------------------------------------------

    def _changed(self) -> None:
        self.version += 1
        event, self._event = self._event, asyncio.Event()
        event.set()

    def _save(self, force: bool = False) -> None:
        if not (self._dirty and self.engine and self.store and self.slug and self.playthrough_id):
            return
        now = self.clock()
        if not force and now - self._saved_at < SAVE_EVERY_S:
            return
        self.store.save_playthrough(self.slug, self.playthrough_id, self.engine.record())
        self._dirty = False
        self._saved_at = now
