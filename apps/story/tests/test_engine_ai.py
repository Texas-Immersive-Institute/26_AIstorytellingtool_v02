import random

from story_app.ai_writer import build_prompt
from story_app.engine import Engine
from story_app.matching import EmbeddingMatcher
from test_engine import Clock, events, lighthouse, run_until, say, until_window


def start(ai_timeout=10.0, mode="live"):
    clock = Clock()
    engine = Engine(
        lighthouse(),
        now=clock.now,
        rng=random.Random(1),
        ai_timeout=ai_timeout,
        ai_label="Fake AI",
        mode=mode,
    )
    return engine, clock


def to_line(engine, clock, line_id):
    run_until(
        engine,
        clock,
        lambda: (
            (engine.pending_ai is not None)
            or (engine.shown.line and engine.shown.line["id"] == line_id)
        ),
    )


def test_no_audience_input_means_default_lines_and_no_ai_calls():
    engine, clock = start()
    run_until(engine, clock, lambda: engine.ended)
    assert not events(engine, "ai_requested")
    assert all(e["source"] in {"authored", "default"} for e in events(engine, "line_shown"))


def test_outline_only_never_uses_ai():
    engine, clock = start(mode="outline_only")
    assert engine.ai_timeout is None
    until_window(engine, clock, "influence")
    say(engine, clock, "ana", "Pickles")
    run_until(engine, clock, lambda: engine.ended)
    assert not events(engine, "ai_requested")


def test_influence_fill_and_ai_line_with_memory_and_profile_notes():
    engine, clock = start()
    until_window(engine, clock, "influence")
    say(engine, clock, "ana", "call him Captain Pickles")
    say(engine, clock, "ben", "Pickles!!")
    engine.close_window(clock.now)

    fill = engine.pending_ai
    assert fill and fill.kind == "fill"
    assert fill.context["variable"]["name"] == "dog_name"
    assert [m["text"] for m in fill.context["messages"]][:2]
    system, prompt = build_prompt(fill)
    assert "dog_name" in prompt and "Captain Pickles" in prompt and "JSON" in system
    engine.resolve_ai(
        clock.now, fill.id, {"value": "Pickles", "backend": "Fake AI", "seconds": 0.5}
    )
    assert engine.variables["dog_name"] == "Pickles"

    line = engine.pending_ai
    assert line and line.kind == "line"
    assert line.context["speaker"] == "Mara" and "drowned rat" in line.context["default_line"]
    assert "Captain Pickles" in " ".join(line.context["audience"])
    system, prompt = build_prompt(line)
    assert "INTENT:" in prompt and "Mara (speaking)" in prompt
    engine.resolve_ai(
        clock.now,
        line.id,
        {
            "line": "Hush, Pickles. Captains don't bark.",
            "memory": ["The audience named the dog Captain Pickles."],
            "profile": ["Mara is amused despite herself."],
            "backend": "Fake AI",
            "seconds": 1.2,
        },
    )
    assert engine.shown.line["text"] == "Hush, Pickles. Captains don't bark."
    assert engine.shown.line["source"] == "ai"
    assert [m.source for m in engine.memory] == ["seed", "ai"]
    assert engine.live_profiles["mara"] == ["Mara is amused despite herself."]
    assert events(engine, "ai_answered")[-1]["seconds"] == 1.2


def test_ai_timeout_or_error_falls_back_to_default():
    engine, clock = start(ai_timeout=3.0)
    until_window(engine, clock, "influence")
    say(engine, clock, "ana", "Rex")
    engine.close_window(clock.now)
    fill = engine.pending_ai
    engine.resolve_ai(clock.now, fill.id, {"error": "backend exploded", "backend": "Fake AI"})
    assert engine.variables["dog_name"] == "Rex"  # fallback: the top message itself
    line = engine.pending_ai
    assert line.kind == "line"
    engine.tick(clock.advance(10))  # no answer in time
    assert engine.shown.line["source"] == "default"
    assert engine.shown.line["text"].startswith("Quiet, Rex.")
    assert not engine.resolve_ai(
        clock.now, line.id, {"line": "too late"}
    )  # late answers are ignored
    reasons = [e["reason"] for e in events(engine, "ai_fallback")]
    assert "backend exploded" in reasons[0] and reasons[-1] == "no answer in time"


def test_skip_while_waiting_for_ai_uses_the_default():
    engine, clock = start()
    until_window(engine, clock, "influence")
    say(engine, clock, "ana", "Bob")
    engine.close_window(clock.now)
    engine.skip(clock.now)  # don't wait for the fill
    engine.skip(clock.now)  # don't wait for the line
    assert engine.variables["dog_name"] == "Bob"
    assert engine.shown.line["source"] == "default"


def test_tuning_changes_weights_live():
    engine, clock = start(ai_timeout=None)
    until_window(engine, clock, "choice")
    say(engine, clock, "ana", "let him in")
    turn = say(engine, clock, "ben", "turn him away")
    engine.thumbs_up(clock.now, turn.id, "cy")
    totals = {o["id"]: o["total"] for o in engine.snapshot(clock.now)["window"]["options"]}
    assert totals["storm_turn_away"] == 2 * totals["storm_let_in"]
    assert engine.tune(clock.now, thumbs_up_factor=0)
    totals = {o["id"]: o["total"] for o in engine.snapshot(clock.now)["window"]["options"]}
    assert totals["storm_turn_away"] == totals["storm_let_in"]
    assert engine.tune(clock.now, match_threshold=1.0)
    assert engine.snapshot(clock.now)["window"]["unmatched"] == 0  # exact matches still score 1.0
    assert events(engine, "tuned")


class FakeEmbedder:
    """Vectors by keyword so 'go inside' lands near 'let him in'."""

    AXES = (("in", "inside", "open", "help", "let"), ("away", "shut", "send", "keep", "trust"))

    def embed(self, texts):
        out = []
        for t in texts:
            words = t.lower().replace(",", " ").split()
            v = [float(sum(w in axis for w in words)) for axis in self.AXES] + [0.1]
            norm = sum(x * x for x in v) ** 0.5
            out.append([x / norm for x in v])
        return out


def test_embedding_matcher_matches_paraphrases():
    matcher = EmbeddingMatcher(FakeEmbedder())
    let_in = "Let him in open the door, help him, be kind, let the stranger inside"
    away = "Turn him away keep the door shut, send him away, don't trust him"
    a, b = matcher.scores("go inside", [let_in, away])
    assert a > 0.5 > b
    assert matcher.scores("2", [let_in, away])[1] == 1.0  # word overlap rules still apply
