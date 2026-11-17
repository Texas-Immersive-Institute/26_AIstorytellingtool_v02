import json

from conftest import EXAMPLE
from story_app.checks import check_story
from story_app.model import (
    Beat,
    ChoiceOption,
    ChoicePoint,
    Condition,
    Effect,
    Line,
    Scene,
    SceneExit,
    Story,
    StoryVariable,
    new_story,
)


def messages(story, **kw):
    return [(i.level, i.message) for i in check_story(story, **kw)]


def test_example_story_is_clean():
    story = Story.model_validate_json((EXAMPLE / "story.json").read_text(encoding="utf-8"))
    assert check_story(story, lambda rel: (EXAMPLE / rel).is_file()) == []


def test_example_roundtrips_unchanged():
    raw = json.loads((EXAMPLE / "story.json").read_text(encoding="utf-8"))
    assert json.loads(Story.model_validate(raw).model_dump_json()) == raw


def test_new_story_only_warns():
    issues = check_story(new_story("Test"))
    assert all(i.level == "warning" for i in issues)


def test_dangling_links_and_unknown_variables():
    story = Story(
        title="t",
        start_scene="a",
        variables=[StoryVariable(name="trust", type="number", default=1)],
        scenes=[
            Scene(
                id="a",
                title="A",
                steps=[
                    Beat(
                        id="b1",
                        lines=[Line(id="l1", kind="ai", speaker="ghost", intent="x")],
                        visible_when=Condition(variable="nope", op="eq", value=1),
                        effects=[Effect(variable="trust", op="toggle")],
                    )
                ],
                exit=SceneExit(
                    kind="choice",
                    choice=ChoicePoint(
                        prompt="?", options=[ChoiceOption(id="o1", label="go", goes_to="zz")]
                    ),
                ),
            )
        ],
    )
    msgs = [m for _, m in messages(story)]
    assert "Unknown speaker 'ghost'." in msgs
    assert "AI line has no default line." in msgs
    assert "Unknown variable 'nope'." in msgs
    assert "'toggle' needs a flag variable; 'trust' is number." in msgs
    assert "A choice point needs at least two options." in msgs
    assert "Option leads to unknown scene 'zz'." in msgs


def test_unreachable_scene_and_missing_asset():
    story = new_story("t")
    story.scenes.append(Scene(id="orphan", title="Orphan", steps=[Beat(id="x")]))
    story.scenes[0].steps[0].picture.mode = "set"
    story.scenes[0].steps[0].picture.asset = "assets/missing.png"
    msgs = messages(story, asset_exists=lambda rel: False)
    assert ("warning", "No path leads to this scene.") in msgs
    assert ("error", "The picture file 'assets/missing.png' is missing.") in msgs


def test_duplicate_ids():
    story = new_story("t")
    story.scenes[0].steps.append(Beat(id="beat_1"))
    assert ("error", "Duplicate step, lane or line id 'beat_1'.") in messages(story)


def test_unknown_placeholder_in_line():
    story = new_story("t")
    story.scenes[0].steps[0].lines[0].text = "Hello {nobody}"
    assert ("error", "Line uses unknown variable '{nobody}'.") in messages(story)
