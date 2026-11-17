"""The playthrough engine: plays a Story beat by beat, opens choice points and influence
windows, keeps story variables and story memory, and logs every event.

The story is walked by a generator (`_script`) that yields a Wait each time something is on
screen. The engine resumes it when the wait ends: a line's reading time passes, the operator
skips, or a window closes (its result is sent back into the generator). Time is always passed
in by the caller, so tests can run a whole playthrough instantly.

No-input rules (CONTEXT.md, PROJECT.md):
- AI lines play their default line while the playthrough has had no audience input. (Until
  the AI backends land in milestone 5, they always play the default line.)
- A choice point that gets no matched messages picks an option at random with equal odds;
  ties are broken at random.
"""

from __future__ import annotations

import random
import re
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from story_app.matching import LexicalMatcher, Matcher
from story_app.model import (
    Beat,
    ChoiceOption,
    ChoicePoint,
    Condition,
    Effect,
    Lane,
    Line,
    Scene,
    Split,
    Story,
)

Mode = Literal["live", "outline_only"]
LINE_PAD_S = 1.0
INFLUENCE_TOP_N = 3
MAX_FILL_CHARS = 60
MAX_LINE_CHARS = 400
MAX_SCENES_WITHOUT_WAIT = 200
RECENT_LINES = 8
MEMORY_IN_PROMPT = 12
AUDIENCE_IN_PROMPT = 5
AI_GRACE_S = 2.0  # the engine waits a little longer than the backend's own timeout
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


# --- state ---------------------------------------------------------------------------------


@dataclass
class Message:
    id: str
    author: str
    text: str
    t: float
    window_id: str | None
    from_operator: bool = False
    author_id: str | None = None  # the chat device that sent it (None for the operator)
    hidden: bool = False
    thumbs: set[str] = field(default_factory=set)
    scores: dict[str, float] = field(default_factory=dict)  # option id (or "prompt") -> score

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "author": self.author,
            "author_id": self.author_id,
            "text": self.text,
            "t": round(self.t, 2),
            "window_id": self.window_id,
            "from_operator": self.from_operator,
            "hidden": self.hidden,
            "thumbs": len(self.thumbs),
            "scores": self.scores,
        }


@dataclass
class MemoryEntry:
    id: str
    text: str
    about: str | None
    pinned: bool
    source: str  # seed | operator | ai

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "about": self.about,
            "pinned": self.pinned,
            "source": self.source,
        }


@dataclass
class Window:
    id: str
    kind: Literal["choice", "influence"]
    prompt: str
    opened_at: float
    closes_at: float
    options: list[ChoiceOption] = field(default_factory=list)
    fills_variable: str | None = None
    beat_id: str | None = None
    forced: str | None = None  # option id chosen by the operator


@dataclass
class AiRequest:
    """Work for the AI backend. The runner answers it with resolve_ai(); if no answer comes
    before the wait runs out, the engine uses the fallback (the default line, or the top
    message as a variable's value)."""

    id: str
    kind: Literal["line", "fill"]
    context: dict[str, Any]


@dataclass
class Wait:
    kind: Literal["line", "hold", "window", "ai"]
    until: float
    started_at: float
    window: Window | None = None
    request: AiRequest | None = None


@dataclass
class ChoiceResult:
    option: ChoiceOption
    decided_by: str
    totals: dict[str, float]


@dataclass
class InfluenceResult:
    top: list[Message]


@dataclass
class Shown:
    """What is on stage right now."""

    scene_id: str | None = None
    beat_id: str | None = None
    lane_id: str | None = None
    picture: str | None = None
    audio: str | None = None
    line: dict[str, Any] | None = None


# --- engine --------------------------------------------------------------------------------


class Engine:
    def __init__(
        self,
        story: Story,
        *,
        now: float,
        mode: Mode = "live",
        rng: random.Random | None = None,
        matcher: Matcher | None = None,
        ai_timeout: float | None = None,
        ai_label: str | None = None,
    ):
        self.story = story
        self.mode = mode
        self.rng = rng or random.Random()
        self.matcher = matcher or LexicalMatcher()
        # AI is used only when a backend is ready (ai_timeout set) and the mode is live.
        self.ai_timeout = ai_timeout if mode == "live" else None
        self.ai_label = ai_label
        self.tuning: dict[str, float] = {
            "thumbs_up_factor": story.settings.thumbs_up_factor,
            "match_threshold": story.settings.match_threshold,
        }
        self.recent_lines: list[dict[str, Any]] = []
        self._audience_cursor = 0
        self.started_at = now
        self.started_wall = datetime.now(UTC).isoformat()
        self.scenes = {s.id: s for s in story.scenes}
        self.characters = {c.id: c for c in story.characters}
        self.variables: dict[str, Any] = {v.name: v.default for v in story.variables}
        self.memory: list[MemoryEntry] = [
            MemoryEntry(f"seed_{i + 1}", n.text, n.about, n.pinned, "seed")
            for i, n in enumerate(story.memory_seed)
        ]
        self.live_profiles: dict[str, list[str]] = {c.id: [] for c in story.characters}
        self.messages: list[Message] = []
        self.events: list[dict[str, Any]] = []
        self.path: list[str] = []
        self.shown = Shown()
        self.wait: Wait | None = None
        self.paused_at: float | None = None
        self.ended = False
        self.error: str | None = None
        self._seq = 0
        self._waits = 0
        self._ids = 0
        self._now = now
        self._script_gen = self._script()
        self._log(
            "started",
            mode=mode,
            title=story.title,
            ai=ai_label if self.ai_timeout is not None else None,
            matcher=self.matcher.name,
        )
        self._resume(None)

    # --- public controls ---------------------------------------------------------------

    @property
    def has_audience_input(self) -> bool:
        return any(not m.hidden for m in self.messages)

    @property
    def window(self) -> Window | None:
        return self.wait.window if self.wait and self.wait.kind == "window" else None

    @property
    def pending_ai(self) -> AiRequest | None:
        return self.wait.request if self.wait and self.wait.kind == "ai" else None

    def resolve_ai(self, now: float, request_id: str, result: dict[str, Any] | None) -> bool:
        """Deliver the AI's answer. Answers that arrive after the wait ended are ignored."""
        self._now = now
        req = self.pending_ai
        if self.ended or req is None or req.id != request_id:
            return False
        self.wait = None
        self._resume(result)
        return True

    def tune(self, now: float, **values: float) -> bool:
        """Change weighting live for this playthrough (Debug view sliders)."""
        self._now = now
        changed = {
            k: float(v) for k, v in values.items() if k in self.tuning and self.tuning[k] != v
        }
        if not changed:
            return False
        self.tuning.update(changed)
        self._log("tuned", **changed)
        return True

    def tick(self, now: float) -> bool:
        """Advance past any wait whose time is up. Returns True if anything changed."""
        self._now = now
        if self.ended or self.paused_at is not None or self.wait is None:
            return False
        if now < self.wait.until:
            return False
        self._finish_wait(reason="countdown" if self.window else "auto")
        return True

    def skip(self, now: float) -> bool:
        """Move on now. A choice point can only be closed, not skipped."""
        self._now = now
        if self.ended or self.wait is None:
            return False
        if self.window and self.window.kind == "choice":
            return False
        self._finish_wait(reason="operator")
        return True

    def close_window(self, now: float) -> bool:
        self._now = now
        if self.ended or not self.window:
            return False
        self._finish_wait(reason="operator")
        return True

    def add_time(self, now: float, seconds: float) -> bool:
        self._now = now
        win = self.window
        if not win or seconds <= 0:
            return False
        win.closes_at += seconds
        assert self.wait is not None
        self.wait.until = win.closes_at
        self._log("window_extended", window_id=win.id, seconds=seconds)
        return True

    def force_option(self, now: float, option_id: str) -> bool:
        self._now = now
        win = self.window
        if not win or win.kind != "choice" or option_id not in {o.id for o in win.options}:
            return False
        win.forced = option_id
        self._finish_wait(reason="operator")
        return True

    def pause(self, now: float) -> bool:
        self._now = now
        if self.ended or self.paused_at is not None:
            return False
        self.paused_at = now
        self._log("paused")
        return True

    def resume(self, now: float) -> bool:
        self._now = now
        if self.paused_at is None:
            return False
        gap = now - self.paused_at
        if self.wait:
            # Only the paused part of this wait counts (it may have started during the pause).
            held = now - max(self.paused_at, self.wait.started_at)
            self.wait.until += held
            if self.wait.window:
                self.wait.window.closes_at += held
        self.paused_at = None
        self._log("resumed", paused_for=round(gap, 2))
        return True

    def add_message(
        self,
        now: float,
        author: str,
        text: str,
        *,
        from_operator: bool = False,
        author_id: str | None = None,
    ) -> Message | None:
        self._now = now
        text = text.strip()
        if not text or self.ended:
            return None
        win = self.window
        msg = Message(
            id=self._next_id("msg"),
            author=author.strip()[:40] or "audience",
            text=text[:500],
            t=self._rel(now),
            window_id=win.id if win else None,
            from_operator=from_operator,
            author_id=author_id,
        )
        if win:
            msg.scores = self._score(msg.text, win)
        self.messages.append(msg)
        self._log("message", message=msg.public())
        return msg

    def thumbs_up(self, now: float, message_id: str, voter: str) -> bool:
        self._now = now
        msg = self._message(message_id)
        if not msg or voter in {msg.author, msg.author_id} or voter in msg.thumbs:
            return False
        msg.thumbs.add(voter)
        self._log("thumbs_up", message_id=message_id, voter=voter, total=len(msg.thumbs))
        return True

    def hide_message(self, now: float, message_id: str, hidden: bool = True) -> bool:
        self._now = now
        msg = self._message(message_id)
        if not msg or msg.hidden == hidden:
            return False
        msg.hidden = hidden
        self._log("message_hidden" if hidden else "message_shown", message_id=message_id)
        return True

    def add_memory(
        self, now: float, text: str, about: str | None = None, source: str = "operator"
    ) -> MemoryEntry | None:
        self._now = now
        if not text.strip():
            return None
        entry = MemoryEntry(self._next_id("mem"), text.strip(), about, False, source)
        self.memory.append(entry)
        self._log("memory_added", entry=entry.public())
        return entry

    def edit_memory(
        self, now: float, entry_id: str, *, text: str | None = None, pinned: bool | None = None
    ) -> bool:
        self._now = now
        entry = next((m for m in self.memory if m.id == entry_id), None)
        if not entry:
            return False
        if text is not None:
            entry.text = text.strip()
        if pinned is not None:
            entry.pinned = pinned
        self._log("memory_edited", entry=entry.public())
        return True

    def delete_memory(self, now: float, entry_id: str) -> bool:
        self._now = now
        before = len(self.memory)
        self.memory = [m for m in self.memory if m.id != entry_id]
        if len(self.memory) == before:
            return False
        self._log("memory_deleted", entry_id=entry_id)
        return True

    def stop(self, now: float) -> None:
        self._now = now
        if not self.ended:
            self.ended = True
            self.wait = None
            self._log("stopped")

    # --- snapshot / record -------------------------------------------------------------

    def snapshot(self, now: float) -> dict[str, Any]:
        wait = self.wait
        clock = now
        if self.paused_at is not None:
            clock = max(self.paused_at, wait.started_at) if wait else self.paused_at
        win = self.window
        return {
            "title": self.story.title,
            "mode": self.mode,
            "status": "ended"
            if self.ended
            else "paused"
            if self.paused_at is not None
            else "running",
            "error": self.error,
            "elapsed": round(self._rel(now), 2),
            "scene": {"id": self.shown.scene_id, "title": self._scene_title(self.shown.scene_id)},
            "beat_id": self.shown.beat_id,
            "lane_id": self.shown.lane_id,
            "picture": self.shown.picture,
            "audio": self.shown.audio,
            "line": self.shown.line,
            "wait": None
            if wait is None
            else {
                "kind": wait.kind,
                "remaining": round(max(0.0, wait.until - clock), 2),
                "length": round(wait.until - wait.started_at, 2),
            },
            "window": None if win is None else self._window_public(win),
            "variables": self.variables,
            "memory": [m.public() for m in self.memory],
            "live_profiles": self.live_profiles,
            "path": self.path,
            "has_audience_input": self.has_audience_input,
            "ai": {
                "enabled": self.ai_timeout is not None,
                "label": self.ai_label,
                "pending": None if self.pending_ai is None else self.pending_ai.kind,
            },
            "matcher": self.matcher.name,
            "tuning": self.tuning,
            "messages": [m.public() for m in self.messages[-200:]],
            "events": self.events[-150:],
        }

    def record(self) -> dict[str, Any]:
        """The saved playthrough: the story as it was, every event, and the final state."""
        return {
            "format": 1,
            "started_at": self.started_wall,
            "mode": self.mode,
            "ended": self.ended,
            "story": self.story.model_dump(mode="json"),
            "events": self.events,
            "final": {
                "variables": self.variables,
                "memory": [m.public() for m in self.memory],
                "live_profiles": self.live_profiles,
                "path": self.path,
            },
        }

    # --- the script --------------------------------------------------------------------

    def _script(self) -> Generator[Wait, Any, None]:
        scene_id = self.story.start_scene
        entries_without_wait = 0
        while scene_id is not None:
            scene = self.scenes.get(scene_id)
            if scene is None:
                self._fail(f"Scene '{scene_id}' does not exist.")
                return
            waits_before = self._waits
            self.path.append(scene.id)
            self.shown.scene_id = scene.id
            self.shown.lane_id = None
            self._log("scene_entered", scene_id=scene.id, title=scene.title)
            for step in scene.steps:
                if self.ended:
                    return
                if isinstance(step, Beat):
                    yield from self._play_beat(step)
                else:
                    lane = yield from self._pick_lane(step)
                    if lane is None:
                        return
                    self.shown.lane_id = lane.id
                    for beat in lane.beats:
                        yield from self._play_beat(beat)
                    self.shown.lane_id = None
            scene_id = yield from self._leave(scene)
            if self.ended:
                return
            entries_without_wait = 0 if self._waits != waits_before else entries_without_wait + 1
            if entries_without_wait > MAX_SCENES_WITHOUT_WAIT:
                self._fail("The story loops between scenes with nothing to show.")
                return
        self.ended = True
        self.wait = None
        self._log("ended", path=self.path)

    def _play_beat(self, beat: Beat) -> Generator[Wait, Any, None]:
        if beat.visible_when is not None and not self._test(beat.visible_when):
            self._log("beat_skipped", beat_id=beat.id, reason="condition")
            return
        self.shown.beat_id = beat.id
        self.shown.line = None
        for slot_name in ("picture", "audio"):
            slot = getattr(beat, slot_name)
            if slot.mode == "set":
                setattr(self.shown, slot_name, slot.asset)
            elif slot.mode == "clear":
                setattr(self.shown, slot_name, None)
        self._log(
            "beat_entered", beat_id=beat.id, picture=self.shown.picture, audio=self.shown.audio
        )
        for eff in beat.effects:
            self._apply(eff, cause=f"beat {beat.id}")

        influence: list[Message] = []
        if beat.influence is not None:
            win = self._open(
                "influence",
                beat.influence.prompt,
                beat.influence.duration_s,
                fills_variable=beat.influence.fills_variable,
                beat_id=beat.id,
            )
            result: InfluenceResult = yield self.wait  # type: ignore[misc]
            influence = result.top
            if win.fills_variable and influence:
                yield from self._fill_variable(win, influence)

        per_line = None
        if beat.duration_s is not None:
            per_line = beat.duration_s / max(1, len(beat.lines))
        if not beat.lines:
            yield self._wait("hold", beat.duration_s or self.story.settings.min_beat_s)
            return
        for line in beat.lines:
            text, source = yield from self._line_text(line, influence)
            self.shown.line = self._line_public(line, text, source)
            speaker = self.characters.get(line.speaker or "")
            self.recent_lines = [
                *self.recent_lines,
                {"speaker": speaker.name if speaker else "Narrator", "text": text},
            ][-RECENT_LINES:]
            self._log(
                "line_shown",
                beat_id=beat.id,
                line_id=line.id,
                text=text,
                source=source,
                speaker=line.speaker,
            )
            yield self._wait("line", per_line or self._reading_time(text, line.action))

    def _pick_lane(self, split: Split) -> Generator[Wait, Any, Lane | None]:
        lanes = {lane.id: lane for lane in split.lanes}
        if split.picked_by == "choice":
            if split.choice is None:
                self._fail(f"Split '{split.id}' has no choice point.")
                return None
            result = yield from self._choose(split.choice, where=f"split {split.id}")
            if result is None:
                return None
            lane_id = result.option.goes_to
        else:
            lane_id = next((r.goes_to for r in split.rules if self._test(r.when)), split.otherwise)
            self._log("lane_picked", split_id=split.id, lane_id=lane_id, by="variable")
        lane = lanes.get(lane_id or "")
        if lane is None:
            self._fail(f"Split '{split.id}' leads to unknown lane '{lane_id}'.")
        return lane

    def _leave(self, scene: Scene) -> Generator[Wait, Any, str | None]:
        ex = scene.exit
        if ex.kind == "end":
            return None
        if ex.kind == "next":
            return ex.goes_to
        if ex.kind == "variable":
            target = next((r.goes_to for r in ex.rules if self._test(r.when)), ex.otherwise)
            self._log("path_picked", scene_id=scene.id, goes_to=target, by="variable")
            return target
        if ex.choice is None:
            self._fail(f"Scene '{scene.id}' has no choice point.")
            return None
        result = yield from self._choose(ex.choice, where=f"scene {scene.id}")
        return None if result is None else result.option.goes_to

    def _choose(self, choice: ChoicePoint, where: str) -> Generator[Wait, Any, ChoiceResult | None]:
        if not choice.options:
            self._fail(f"The choice point in {where} has no options.")
            return None
        self.shown.line = None
        self._open("choice", choice.prompt, choice.countdown_s, options=list(choice.options))
        result: ChoiceResult = yield self.wait  # type: ignore[misc]
        for eff in result.option.effects:
            self._apply(eff, cause=f"choice '{result.option.label}'")
        return result

    # --- waits and windows -------------------------------------------------------------

    def _wait(self, kind: Literal["line", "hold"], seconds: float) -> Wait:
        self._waits += 1
        self.wait = Wait(kind=kind, started_at=self._now, until=self._now + seconds)
        return self.wait

    def _open(
        self,
        kind: Literal["choice", "influence"],
        prompt: str,
        seconds: float,
        *,
        options: list[ChoiceOption] | None = None,
        fills_variable: str | None = None,
        beat_id: str | None = None,
    ) -> Window:
        win = Window(
            id=self._next_id("win"),
            kind=kind,
            prompt=prompt,
            opened_at=self._now,
            closes_at=self._now + seconds,
            options=options or [],
            fills_variable=fills_variable,
            beat_id=beat_id,
        )
        self._waits += 1
        self.wait = Wait(kind="window", started_at=self._now, until=win.closes_at, window=win)
        self._log(
            "window_opened",
            window_id=win.id,
            kind=kind,
            prompt=prompt,
            seconds=seconds,
            options=[{"id": o.id, "label": o.label} for o in win.options],
        )
        return win

    def _finish_wait(self, reason: str) -> None:
        wait = self.wait
        assert wait is not None
        value: Any = None
        if wait.window is not None:
            value = self._close(wait.window, reason)
        self.wait = None
        self._resume(value)

    def _resume(self, value: Any) -> None:
        try:
            self._script_gen.send(value)
        except StopIteration:
            if not self.ended:
                self.ended = True
                self.wait = None
                self._log("ended", path=self.path)

    def _close(self, win: Window, reason: str) -> ChoiceResult | InfluenceResult:
        msgs = [m for m in self.messages if m.window_id == win.id and not m.hidden]
        if win.kind == "influence":
            ranked = sorted(msgs, key=lambda m: self._influence_weight(m), reverse=True)
            top = ranked[:INFLUENCE_TOP_N]
            self._log(
                "window_closed",
                window_id=win.id,
                kind="influence",
                reason=reason,
                messages=len(msgs),
                top=[
                    {"id": m.id, "text": m.text, "weight": round(self._influence_weight(m), 3)}
                    for m in top
                ],
            )
            return InfluenceResult(top=top)

        totals = self._totals(win, msgs)
        if win.forced:
            option = next(o for o in win.options if o.id == win.forced)
            decided_by = "operator"
        else:
            best = max(totals.values(), default=0.0)
            if best <= 0:
                option = self.rng.choice(win.options)
                decided_by = "random (no input)" if not msgs else "random (nothing matched)"
            else:
                leaders = [o for o in win.options if totals[o.id] == best]
                option = self.rng.choice(leaders) if len(leaders) > 1 else leaders[0]
                decided_by = "audience (tie broken at random)" if len(leaders) > 1 else "audience"
        self._log(
            "window_closed",
            window_id=win.id,
            kind="choice",
            reason=reason,
            messages=len(msgs),
            totals={k: round(v, 3) for k, v in totals.items()},
            chosen=option.id,
            chosen_label=option.label,
            decided_by=decided_by,
        )
        return ChoiceResult(option=option, decided_by=decided_by, totals=totals)

    def _window_public(self, win: Window) -> dict[str, Any]:
        msgs = [m for m in self.messages if m.window_id == win.id and not m.hidden]
        public: dict[str, Any] = {
            "id": win.id,
            "kind": win.kind,
            "prompt": win.prompt,
            "fills_variable": win.fills_variable,
            "message_count": len(msgs),
        }
        if win.kind == "choice":
            totals = self._totals(win, msgs)
            threshold = self.tuning["match_threshold"]
            public["options"] = [
                {
                    "id": o.id,
                    "label": o.label,
                    "total": round(totals[o.id], 3),
                    "messages": sum(
                        1 for m in msgs if self._best_option(m, win, threshold) == o.id
                    ),
                }
                for o in win.options
            ]
            public["unmatched"] = sum(
                1 for m in msgs if self._best_option(m, win, threshold) is None
            )
        else:
            ranked = sorted(msgs, key=self._influence_weight, reverse=True)
            public["top"] = [
                {"id": m.id, "text": m.text, "weight": round(self._influence_weight(m), 3)}
                for m in ranked[:INFLUENCE_TOP_N]
            ]
        return public

    # --- scoring -------------------------------------------------------------------------

    def _score(self, text: str, win: Window) -> dict[str, float]:
        if win.kind == "choice":
            cands = [f"{o.label} {o.meaning}" for o in win.options]
            return dict(
                zip([o.id for o in win.options], self.matcher.scores(text, cands), strict=True)
            )
        return {"prompt": self.matcher.scores(text, [win.prompt])[0]}

    def _boost(self, msg: Message) -> float:
        return 1 + len(msg.thumbs) * self.tuning["thumbs_up_factor"]

    def _best_option(self, msg: Message, win: Window, threshold: float) -> str | None:
        if not msg.scores:
            return None
        option_id, score = max(msg.scores.items(), key=lambda kv: kv[1])
        return option_id if score >= threshold and score > 0 else None

    def _totals(self, win: Window, msgs: list[Message]) -> dict[str, float]:
        threshold = self.tuning["match_threshold"]
        totals = {o.id: 0.0 for o in win.options}
        for m in msgs:
            best = self._best_option(m, win, threshold)
            if best is not None:
                totals[best] += m.scores[best] * self._boost(m)
        return totals

    def _influence_weight(self, msg: Message) -> float:
        # Relevance to the prompt matters, but any message can surface if the room backs it.
        return (0.25 + msg.scores.get("prompt", 0.0)) * self._boost(msg)

    # --- variables and lines -----------------------------------------------------------

    def _test(self, cond: Condition) -> bool:
        value = self.variables.get(cond.variable)
        op, target = cond.op, cond.value
        if op == "is_set":
            return value not in (None, "", False)
        if op == "not_set":
            return value in (None, "", False)
        if op == "eq":
            return value == target
        if op == "ne":
            return value != target
        if op == "contains":
            return isinstance(value, str) and str(target or "").lower() in value.lower()
        try:
            a, b = float(value), float(target)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return {"lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[op]

    def _apply(self, eff: Effect, cause: str) -> None:
        if eff.variable not in self.variables:
            self._log("warning", message=f"Unknown variable '{eff.variable}'.")
            return
        old = self.variables[eff.variable]
        if eff.op == "set":
            new = eff.value
        elif eff.op == "add":
            new = (old or 0) + (eff.value or 0)
        elif eff.op == "toggle":
            new = not bool(old)
        else:
            new = None
        self._set(eff.variable, new, cause)

    def _set(self, name: str, value: Any, cause: str) -> None:
        old = self.variables.get(name)
        if old == value:
            return
        self.variables[name] = value
        self._log("variable_changed", name=name, old=old, new=value, cause=cause)

    # --- AI --------------------------------------------------------------------------

    @property
    def _ai_ready(self) -> bool:
        # No-input rule: until the audience has said anything, AI lines play their default.
        return self.ai_timeout is not None and self.has_audience_input

    def _ask_ai(self, kind: Literal["line", "fill"], context: dict[str, Any]) -> Wait:
        req = AiRequest(id=self._next_id("ai"), kind=kind, context=context)
        assert self.ai_timeout is not None
        self._waits += 1
        self.wait = Wait(
            kind="ai",
            started_at=self._now,
            until=self._now + self.ai_timeout + AI_GRACE_S,
            request=req,
        )
        self._log("ai_requested", request_id=req.id, kind=kind, context=context)
        return self.wait

    def _fill_variable(self, win: Window, top: list[Message]) -> Generator[Wait, Any, None]:
        """Fill a variable from the influence window's top messages: the AI picks the value;
        without it (or if it gives nothing) the top message itself, trimmed, is used."""
        name = win.fills_variable
        assert name is not None
        fallback = top[0].text.strip().strip(".!?\"'")[:MAX_FILL_CHARS]
        if self._ai_ready:
            var = next((v for v in self.story.variables if v.name == name), None)
            result = yield self._ask_ai(
                "fill",
                {
                    **self._story_context(None),
                    "variable": {
                        "name": name,
                        "type": var.type if var else "text",
                        "description": var.description if var else "",
                    },
                    "question": win.prompt,
                    "messages": [
                        {"text": m.text, "weight": round(self._influence_weight(m), 3)} for m in top
                    ],
                },
            )
            value = self._coerce(name, (result or {}).get("value"))
            self._log_ai_result(result, value)
            if value is not None:
                self._absorb_notes(result, None)
                self._set(name, value, cause=f"influence window (AI read {len(top)} message(s))")
                return
        value = self._coerce(name, fallback)
        if value is not None:
            self._set(name, value, cause=f"influence window (message {top[0].id})")

    def _line_text(
        self, line: Line, influence: list[Message]
    ) -> Generator[Wait, Any, tuple[str, str]]:
        default = self._interpolate(line.text)
        if line.kind == "authored":
            return default, "authored"
        if not self._ai_ready:
            return default, "default"
        speaker = self.characters.get(line.speaker or "")
        audience = [m.text for m in influence] or self._recent_audience()
        result = yield self._ask_ai(
            "line",
            {
                **self._story_context(speaker.id if speaker else None),
                "speaker": speaker.name if speaker else "Narrator",
                "intent": line.intent,
                "default_line": default,
                "action": line.action,
                "audience": audience,
            },
        )
        text = str((result or {}).get("line") or "").strip().strip('"').strip()[:MAX_LINE_CHARS]
        self._log_ai_result(result, text or None)
        if not text:
            return default, "default"
        self._absorb_notes(result, speaker.id if speaker else None)
        return text, "ai"

    def _story_context(self, speaker_id: str | None) -> dict[str, Any]:
        """What the AI is told about the story so far."""
        scene = self.scenes.get(self.shown.scene_id or "")
        memory = sorted(self.memory, key=lambda m: not m.pinned)[:MEMORY_IN_PROMPT]
        return {
            "story": {"title": self.story.title, "description": self.story.description},
            "scene": {"title": scene.title, "summary": scene.summary} if scene else None,
            "characters": [
                {
                    "name": c.name,
                    "speaking": c.id == speaker_id,
                    "profile": c.base_profile.model_dump(),
                    "live_profile": self.live_profiles.get(c.id, []),
                }
                for c in self.story.characters
            ],
            "variables": [
                {"name": v.name, "value": self.variables.get(v.name), "description": v.description}
                for v in self.story.variables
            ],
            "memory": [m.text for m in memory],
            "recent_lines": self.recent_lines,
        }

    def _recent_audience(self) -> list[str]:
        """Messages since the last AI line (or the latest few), for lines without a window."""
        fresh = [m for m in self.messages[self._audience_cursor :] if not m.hidden]
        self._audience_cursor = len(self.messages)
        pool = fresh or [m for m in self.messages if not m.hidden]
        return [m.text for m in pool[-AUDIENCE_IN_PROMPT:]]

    def _absorb_notes(self, result: dict[str, Any] | None, speaker_id: str | None) -> None:
        if not result:
            return
        for note in [str(n).strip() for n in (result.get("memory") or [])][:2]:
            if note:
                self.add_memory(self._now, note, about=speaker_id, source="ai")
        if speaker_id:
            for note in [str(n).strip() for n in (result.get("profile") or [])][:1]:
                if note:
                    self.live_profiles.setdefault(speaker_id, []).append(note)
                    self._log("live_profile_added", character=speaker_id, note=note)

    def _log_ai_result(self, result: dict[str, Any] | None, used: Any) -> None:
        if result is None:
            self._log("ai_fallback", reason="no answer in time")
        elif result.get("error"):
            self._log(
                "ai_fallback", reason=str(result["error"])[:300], backend=result.get("backend")
            )
        else:
            self._log(
                "ai_answered",
                backend=result.get("backend"),
                seconds=result.get("seconds"),
                used=used,
                raw={k: v for k, v in result.items() if k not in {"backend", "seconds"}},
            )
            if used is None:
                self._log("ai_fallback", reason="the answer was empty")

    def _coerce(self, name: str, value: Any) -> Any:
        """Shape an AI or chat value to the variable's type; None if it doesn't fit."""
        if value is None:
            return None
        var = next((v for v in self.story.variables if v.name == name), None)
        kind = var.type if var else "text"
        if kind == "number":
            try:
                return float(value) if "." in str(value) else int(str(value).strip())
            except ValueError:
                return None
        if kind == "flag":
            text = str(value).strip().lower()
            return (
                True
                if text in {"true", "yes", "y", "1"}
                else False
                if text in {"false", "no", "n", "0"}
                else None
            )
        text = str(value).strip().strip(".!?\"'")[:MAX_FILL_CHARS]
        return text or None

    def _interpolate(self, text: str) -> str:
        def sub(m: re.Match[str]) -> str:
            value = self.variables.get(m.group(1))
            return m.group(0) if value is None else str(value)

        return PLACEHOLDER.sub(sub, text)

    def _line_public(self, line: Line, text: str, source: str) -> dict[str, Any]:
        speaker = self.characters.get(line.speaker or "")
        return {
            "id": line.id,
            "speaker": speaker.id if speaker else None,
            "speaker_name": speaker.name if speaker else None,
            "color": speaker.color if speaker else None,
            "portrait": speaker.portraits[0] if speaker and speaker.portraits else None,
            "text": text,
            "action": line.action,
            "kind": line.kind,
            "source": source,
        }

    def _reading_time(self, text: str, action: str) -> float:
        s = self.story.settings
        return max(s.min_beat_s, (len(text) + len(action)) / s.reading_chars_per_s + LINE_PAD_S)

    # --- helpers -----------------------------------------------------------------------

    def _fail(self, message: str) -> None:
        self.error = message
        self.ended = True
        self.wait = None
        self._log("error", message=message)

    def _message(self, message_id: str) -> Message | None:
        return next((m for m in self.messages if m.id == message_id), None)

    def _scene_title(self, scene_id: str | None) -> str | None:
        scene = self.scenes.get(scene_id or "")
        return scene.title if scene else None

    def _next_id(self, prefix: str) -> str:
        self._ids += 1
        return f"{prefix}_{self._ids}"

    def _rel(self, now: float) -> float:
        return now - self.started_at

    def _log(self, event_type: str, /, **data: Any) -> None:
        self._seq += 1
        self.events.append(
            {"seq": self._seq, "t": round(self._rel(self._now), 2), "type": event_type, **data}
        )
