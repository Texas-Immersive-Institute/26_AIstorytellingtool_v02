import json
import random

import pytest
from conftest import EXAMPLE
from story_app.engine import Engine
from story_app.model import Beat, Line, Scene, SceneExit, Story


class Clock:
    def __init__(self):
        self.now = 1000.0

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


def lighthouse() -> Story:
    return Story.model_validate_json((EXAMPLE / "story.json").read_text(encoding="utf-8"))


def start(story=None, seed=1, **kw):
    clock = Clock()
    engine = Engine(story or lighthouse(), now=clock.now, rng=random.Random(seed), **kw)
    return engine, clock


def run_until(engine, clock, done, step=0.5, limit=20000):
    for _ in range(limit):
        if done():
            return
        engine.tick(clock.advance(step))
    raise AssertionError("condition never reached")


def until_window(engine, clock, kind=None):
    run_until(
        engine,
        clock,
        lambda: engine.window is not None and (kind is None or engine.window.kind == kind),
    )
    return engine.window


def events(engine, kind):
    return [e for e in engine.events if e["type"] == kind]


def say(engine, clock, author, text):
    return engine.add_message(clock.now, author, text)


def test_no_input_playthrough_finishes_with_random_choices_and_default_lines():
    engine, clock = start()
    run_until(engine, clock, lambda: engine.ended)
    assert engine.error is None
    assert engine.path[0] == "storm" and engine.path[-1] in {"dawn", "dark"}
    closed = [e for e in events(engine, "window_closed") if e["kind"] == "choice"]
    assert closed and all(e["decided_by"] == "random (no input)" for e in closed)
    lines = {e["line_id"]: e for e in events(engine, "line_shown")}
    assert lines["storm_3a"]["text"] == "Quiet, Biscuit. It's only a drowned rat."
    assert lines["storm_3a"]["source"] == "default"
    json.dumps(engine.record())  # the saved playthrough is plain JSON


def test_influence_window_fills_a_text_variable_used_by_later_lines():
    engine, clock = start()
    win = until_window(engine, clock, "influence")
    assert win.fills_variable == "dog_name"
    say(engine, clock, "ana", "Pickles!")
    say(engine, clock, "ben", "call him pickles")
    engine.thumbs_up(clock.now, engine.messages[0].id, "ben")
    run_until(engine, clock, lambda: engine.window is None)
    assert engine.variables["dog_name"] == "Pickles"
    run_until(engine, clock, lambda: engine.shown.line and engine.shown.line["id"] == "storm_3a")
    assert engine.shown.line["text"].startswith("Quiet, Pickles.")


def test_audience_choice_wins_and_applies_effects():
    engine, clock = start()
    until_window(engine, clock, "choice")
    say(engine, clock, "ana", "let him in")
    say(engine, clock, "ben", "open the door and help him")
    say(engine, clock, "cy", "keep the door shut")
    snap = engine.snapshot(clock.now)
    totals = {o["id"]: o["total"] for o in snap["window"]["options"]}
    assert totals["storm_let_in"] > totals["storm_turn_away"] > 0
    engine.close_window(clock.now)
    assert engine.path[-1] == "fire"
    assert engine.variables["mara_trust"] == 3
    assert events(engine, "window_closed")[-1]["decided_by"] == "audience"


def test_thumbs_up_can_flip_a_choice():
    engine, clock = start()
    until_window(engine, clock, "choice")
    say(engine, clock, "ana", "let him in")
    turn = say(engine, clock, "ben", "turn him away")
    for voter in ("cy", "di", "ed"):
        engine.thumbs_up(clock.now, turn.id, voter)
    assert not engine.thumbs_up(clock.now, turn.id, "ben")  # no thumbs-up on your own message
    assert not engine.thumbs_up(clock.now, turn.id, "cy")  # one per person
    engine.close_window(clock.now)
    assert engine.path[-1] == "tower"


def test_hidden_messages_do_not_count():
    engine, clock = start(seed=3)
    until_window(engine, clock, "choice")
    msg = say(engine, clock, "troll", "turn him away")
    engine.hide_message(clock.now, msg.id)
    say(engine, clock, "ana", "let him in")
    engine.close_window(clock.now)
    assert engine.path[-1] == "fire"


def test_tie_is_broken_at_random():
    engine, clock = start()
    until_window(engine, clock, "choice")
    say(engine, clock, "ana", "let him in")
    say(engine, clock, "ben", "turn him away")
    engine.close_window(clock.now)
    closed = events(engine, "window_closed")[-1]
    assert closed["totals"]["storm_let_in"] == closed["totals"]["storm_turn_away"]
    assert closed["decided_by"] == "audience (tie broken at random)"


def test_variable_split_and_conditional_beat():
    engine, clock = start()
    until_window(engine, clock, "choice")
    engine.force_option(clock.now, "storm_turn_away")  # trust 2 - 2 = 0
    assert engine.variables["mara_trust"] == 0
    run_until(engine, clock, lambda: engine.shown.lane_id is not None)
    assert engine.shown.lane_id == "tower_lane_bitter"
    run_until(engine, clock, lambda: engine.path[-1] == "lamp")
    run_until(engine, clock, lambda: engine.window is not None)
    skipped = [e["beat_id"] for e in events(engine, "beat_skipped")]
    assert "lamp_2" in skipped  # only plays when mara_trust >= 3


def test_controls_pause_skip_add_time_force():
    engine, clock = start()
    first = engine.shown.line["id"]
    engine.pause(clock.now)
    clock.advance(60)
    assert not engine.tick(clock.now)  # paused: nothing moves
    engine.resume(clock.now)
    assert engine.shown.line["id"] == first
    assert engine.skip(clock.now)
    assert engine.shown.line["id"] != first
    win = until_window(engine, clock, "influence")
    assert engine.skip(clock.now)  # skipping closes an influence window
    win = until_window(engine, clock, "choice")
    closes = win.closes_at
    engine.add_time(clock.now, 15)
    assert win.closes_at == closes + 15
    assert not engine.skip(clock.now)  # a choice must be closed, not skipped
    assert not engine.force_option(clock.now, "nope")
    assert engine.force_option(clock.now, "storm_let_in")
    assert events(engine, "window_closed")[-1]["decided_by"] == "operator"


def test_memory_starts_from_seed_and_can_be_edited():
    engine, clock = start()
    assert [m.source for m in engine.memory] == ["seed"]
    entry = engine.add_memory(clock.now, "The audience thinks Tobin is a spy.")
    engine.edit_memory(clock.now, entry.id, pinned=True)
    assert engine.memory[-1].pinned
    engine.delete_memory(clock.now, engine.memory[0].id)
    assert [m.text for m in engine.memory] == ["The audience thinks Tobin is a spy."]


def test_messages_outside_windows_count_as_input_but_score_nothing():
    engine, clock = start()
    assert not engine.has_audience_input
    msg = say(engine, clock, "ana", "hello!")
    assert engine.has_audience_input and msg.window_id is None and msg.scores == {}


def test_loop_with_nothing_to_show_stops_with_an_error():
    story = Story(
        title="loop",
        start_scene="a",
        scenes=[Scene(id="a", title="A", exit=SceneExit(kind="next", goes_to="a"))],
    )
    engine, _ = start(story)
    assert engine.ended and "loops" in engine.error


@pytest.mark.parametrize("seed", range(8))
def test_every_seed_reaches_an_ending(seed):
    engine, clock = start(seed=seed)
    run_until(engine, clock, lambda: engine.ended)
    assert engine.error is None and events(engine, "ended")


def test_beat_duration_and_holds():
    story = Story(
        title="t",
        start_scene="a",
        scenes=[
            Scene(
                id="a",
                title="A",
                steps=[
                    Beat(
                        id="b1",
                        duration_s=10,
                        lines=[Line(id="l1", text="x"), Line(id="l2", text="y")],
                    ),
                    Beat(id="b2"),
                ],
            )
        ],
    )
    engine, clock = start(story)
    assert engine.wait.until - engine.wait.started_at == 5  # 10 s split over two lines
    engine.skip(clock.now)
    engine.skip(clock.now)
    assert engine.wait.kind == "hold"
    engine.skip(clock.now)
    assert engine.ended
