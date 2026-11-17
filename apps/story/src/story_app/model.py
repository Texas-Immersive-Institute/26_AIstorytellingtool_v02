"""The story project format (story.json). Terms follow apps/story/CONTEXT.md.

Structure:
    Story
      characters[]   base profiles (live profiles exist only in a playthrough)
      variables[]    story variables (number, flag or text)
      memory_seed[]  story memory the playthrough starts with
      scenes[]       boxes on the story graph
        steps[]      left to right: a Beat, or a Split into stacked Lanes that rejoin
        exit         where the story goes next: next scene, choice point, variable rule, or end
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

Value = int | float | bool | str | None
NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


# --- variables, conditions, effects -------------------------------------------------


class StoryVariable(Model):
    """A named value defined in the outline that choices and the audience can change."""

    name: str = Field(pattern=NAME_PATTERN)
    type: Literal["number", "flag", "text"]
    default: Value = None
    description: str = ""


class Condition(Model):
    """A test on one story variable, e.g. mara_trust lt 2."""

    variable: str
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "is_set", "not_set", "contains"]
    value: Value = None


class Effect(Model):
    """A change to one story variable, e.g. mara_trust add -1."""

    variable: str
    op: Literal["set", "add", "toggle", "clear"]
    value: Value = None


# --- characters and memory ------------------------------------------------------------


class BaseProfile(Model):
    summary: str = ""
    personality: str = ""
    motivations: str = ""
    speaking_style: str = ""
    knows: str = ""
    hides: str = ""


class Character(Model):
    id: str
    name: str
    color: str = "#8a8f98"
    base_profile: BaseProfile = Field(default_factory=BaseProfile)
    portraits: list[str] = Field(default_factory=list)  # asset paths, first is the default


class MemoryNote(Model):
    text: str
    about: str | None = None  # character id, or None for the whole story
    pinned: bool = False


# --- beats ---------------------------------------------------------------------------


class MediaSlot(Model):
    """hold = keep what the previous beat showed or played; set = use asset; clear = nothing."""

    mode: Literal["hold", "set", "clear"] = "hold"
    asset: str | None = None


class Line(Model):
    """Authored line, or an AI line whose `text` is its default line."""

    id: str
    speaker: str | None = None  # character id; None means narrator
    kind: Literal["authored", "ai"] = "authored"
    text: str = ""
    intent: str = ""  # AI lines: what the line should do
    action: str = ""  # stage direction shown with the line


class InfluenceWindow(Model):
    prompt: str = ""  # what the audience is asked
    duration_s: float = Field(default=30, gt=0)
    fills_variable: str | None = None


class Beat(Model):
    kind: Literal["beat"] = "beat"
    id: str
    title: str = ""
    picture: MediaSlot = Field(default_factory=MediaSlot)
    audio: MediaSlot = Field(default_factory=MediaSlot)
    lines: list[Line] = Field(default_factory=list)
    influence: InfluenceWindow | None = None
    duration_s: float | None = Field(default=None, gt=0)  # None = automatic from text/audio
    visible_when: Condition | None = None
    effects: list[Effect] = Field(default_factory=list)


# --- choices, lanes, scene exits -----------------------------------------------------


class ChoiceOption(Model):
    id: str
    label: str
    meaning: str = ""  # extra description used when matching chat to this option
    goes_to: str | None = None  # a scene id (scene exit) or a lane id (split)
    effects: list[Effect] = Field(default_factory=list)


class ChoicePoint(Model):
    prompt: str = ""
    options: list[ChoiceOption] = Field(default_factory=list)
    countdown_s: float = Field(default=30, gt=0)


class Lane(Model):
    id: str
    label: str = ""
    beats: list[Beat] = Field(default_factory=list)


class LaneRule(Model):
    when: Condition
    goes_to: str  # lane id


class Split(Model):
    """Stacked lanes inside a scene. Exactly one lane plays, then the scene continues."""

    kind: Literal["split"] = "split"
    id: str
    picked_by: Literal["choice", "variable"] = "choice"
    choice: ChoicePoint | None = None  # option.goes_to = lane id
    rules: list[LaneRule] = Field(default_factory=list)
    otherwise: str | None = None  # lane id when no rule matches
    lanes: list[Lane] = Field(default_factory=list)


Step = Annotated[Beat | Split, Field(discriminator="kind")]


class ExitRule(Model):
    when: Condition
    goes_to: str


class SceneExit(Model):
    kind: Literal["next", "choice", "variable", "end"] = "end"
    goes_to: str | None = None  # kind == next
    choice: ChoicePoint | None = None  # kind == choice; option.goes_to = scene id
    rules: list[ExitRule] = Field(default_factory=list)  # kind == variable
    otherwise: str | None = None


class Point(Model):
    x: float = 0
    y: float = 0


class Scene(Model):
    id: str
    title: str
    summary: str = ""
    position: Point = Field(default_factory=Point)
    steps: list[Step] = Field(default_factory=list)
    exit: SceneExit = Field(default_factory=SceneExit)


# --- the story -----------------------------------------------------------------------


class StorySettings(Model):
    stage_style: Literal["visual_novel", "subtitles"] = "visual_novel"
    reading_chars_per_s: float = Field(default=15, gt=0)
    min_beat_s: float = Field(default=2.5, gt=0)
    thumbs_up_factor: float = Field(default=1.0, ge=0)
    match_threshold: float = Field(default=0.35, ge=0, le=1)


class Story(Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    title: str
    description: str = ""
    start_scene: str | None = None
    settings: StorySettings = Field(default_factory=StorySettings)
    characters: list[Character] = Field(default_factory=list)
    variables: list[StoryVariable] = Field(default_factory=list)
    memory_seed: list[MemoryNote] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)


def new_story(title: str) -> Story:
    """A fresh story with one empty scene, ready to edit."""
    scene = Scene(
        id="scene_1",
        title="Opening",
        steps=[Beat(id="beat_1", lines=[Line(id="line_1", text="")])],
    )
    return Story(title=title, start_scene=scene.id, scenes=[scene])
