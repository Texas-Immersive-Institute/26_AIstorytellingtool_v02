"""Story checks: problems an author should fix before (or while) running a playthrough.

The schema in model.py guarantees shape; these checks cover meaning: dangling links,
unknown variables, AI lines without a default line, unreachable scenes, missing assets.
Errors would break a playthrough; warnings are worth a look.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Literal

from pydantic import BaseModel

from story_app.model import (
    Beat,
    ChoicePoint,
    Condition,
    Effect,
    Scene,
    Split,
    Story,
    StoryVariable,
)


class Issue(BaseModel):
    level: Literal["error", "warning"]
    where: str
    message: str


NUMERIC_OPS = {"lt", "le", "gt", "ge"}
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def placeholders(text: str) -> list[str]:
    """Variable names written as {name} in a line."""
    return PLACEHOLDER.findall(text)


def check_story(story: Story, asset_exists: Callable[[str], bool] | None = None) -> list[Issue]:
    issues: list[Issue] = []

    def err(where: str, msg: str) -> None:
        issues.append(Issue(level="error", where=where, message=msg))

    def warn(where: str, msg: str) -> None:
        issues.append(Issue(level="warning", where=where, message=msg))

    scenes = {s.id: s for s in story.scenes}
    variables = {v.name: v for v in story.variables}
    characters = {c.id for c in story.characters}

    _duplicates("scene", (s.id for s in story.scenes), err)
    _duplicates("character", (c.id for c in story.characters), err)
    _duplicates("variable", (v.name for v in story.variables), err)
    _duplicates("step, lane or line", _all_inner_ids(story), err)

    for var in story.variables:
        if var.default is not None and not _value_fits(var, var.default):
            err(f"variables/{var.name}", f"default {var.default!r} is not a {var.type}")

    if not story.scenes:
        err("story", "The story has no scenes.")
    elif story.start_scene is None:
        err("story", "No start scene is set.")
    elif story.start_scene not in scenes:
        err("story", f"Start scene '{story.start_scene}' does not exist.")

    def check_condition(where: str, cond: Condition) -> None:
        var = variables.get(cond.variable)
        if var is None:
            err(where, f"Unknown variable '{cond.variable}'.")
            return
        if cond.op in NUMERIC_OPS and var.type != "number":
            err(where, f"'{cond.op}' needs a number variable; '{var.name}' is {var.type}.")
        if cond.op == "contains" and var.type != "text":
            err(where, f"'contains' needs a text variable; '{var.name}' is {var.type}.")
        if cond.op not in {"is_set", "not_set"} and cond.value is None:
            err(where, f"Condition on '{var.name}' needs a value.")

    def check_effect(where: str, eff: Effect) -> None:
        var = variables.get(eff.variable)
        if var is None:
            err(where, f"Unknown variable '{eff.variable}'.")
            return
        if eff.op == "add" and var.type != "number":
            err(where, f"'add' needs a number variable; '{var.name}' is {var.type}.")
        if eff.op == "toggle" and var.type != "flag":
            err(where, f"'toggle' needs a flag variable; '{var.name}' is {var.type}.")
        if eff.op in {"set", "add"} and eff.value is None:
            err(where, f"Effect on '{var.name}' needs a value.")
        if eff.op == "set" and eff.value is not None and not _value_fits(var, eff.value):
            err(where, f"{eff.value!r} is not a {var.type} for '{var.name}'.")

    def check_choice(where: str, choice: ChoicePoint | None, targets: set[str], kind: str) -> None:
        if choice is None:
            err(where, "Choice point is missing.")
            return
        if len(choice.options) < 2:
            err(where, "A choice point needs at least two options.")
        if not choice.prompt.strip():
            warn(where, "The choice point has no prompt for the audience.")
        for opt in choice.options:
            ow = f"{where}/options/{opt.id}"
            if not opt.label.strip():
                err(ow, "Option has no label.")
            if opt.goes_to is None:
                err(ow, f"Option does not lead to a {kind}.")
            elif opt.goes_to not in targets:
                err(ow, f"Option leads to unknown {kind} '{opt.goes_to}'.")
            for i, eff in enumerate(opt.effects):
                check_effect(f"{ow}/effects/{i}", eff)

    def check_beat(where: str, beat: Beat) -> None:
        for slot_name in ("picture", "audio"):
            slot = getattr(beat, slot_name)
            if slot.mode == "set":
                if not slot.asset:
                    err(where, f"The {slot_name} is set to show an asset but none is chosen.")
                elif asset_exists and not asset_exists(slot.asset):
                    err(where, f"The {slot_name} file '{slot.asset}' is missing.")
        for line in beat.lines:
            lw = f"{where}/lines/{line.id}"
            if line.speaker is not None and line.speaker not in characters:
                err(lw, f"Unknown speaker '{line.speaker}'.")
            for name in placeholders(line.text):
                if name not in variables:
                    err(lw, f"Line uses unknown variable '{{{name}}}'.")
            if line.kind == "ai":
                if not line.text.strip():
                    err(lw, "AI line has no default line.")
                if not line.intent.strip():
                    warn(lw, "AI line has no intent; the AI will have little to go on.")
            elif not line.text.strip() and not line.action.strip():
                warn(lw, "Line is empty.")
        if beat.influence is not None:
            target = beat.influence.fills_variable
            if target is not None:
                var = variables.get(target)
                if var is None:
                    err(where, f"Influence window fills unknown variable '{target}'.")
                elif var.type != "text":
                    warn(where, f"Influence window fills '{target}', which is not a text variable.")
            if not beat.influence.prompt.strip():
                warn(where, "Influence window has no prompt for the audience.")
        if beat.visible_when is not None:
            check_condition(f"{where}/visible_when", beat.visible_when)
        for i, eff in enumerate(beat.effects):
            check_effect(f"{where}/effects/{i}", eff)

    def check_split(where: str, split: Split) -> None:
        lanes = {lane.id for lane in split.lanes}
        if len(split.lanes) < 2:
            err(where, "A split needs at least two lanes.")
        if split.picked_by == "choice":
            check_choice(f"{where}/choice", split.choice, lanes, "lane")
        else:
            if not split.rules:
                err(where, "A variable split needs at least one rule.")
            for i, rule in enumerate(split.rules):
                check_condition(f"{where}/rules/{i}", rule.when)
                if rule.goes_to not in lanes:
                    err(f"{where}/rules/{i}", f"Rule leads to unknown lane '{rule.goes_to}'.")
            if split.otherwise is None:
                err(where, "A variable split needs an 'otherwise' lane.")
            elif split.otherwise not in lanes:
                err(where, f"'otherwise' leads to unknown lane '{split.otherwise}'.")
        for lane in split.lanes:
            if not lane.beats:
                warn(f"{where}/lanes/{lane.id}", "Lane has no beats.")
            for beat in lane.beats:
                check_beat(f"{where}/lanes/{lane.id}/{beat.id}", beat)

    def check_scene(scene: Scene) -> None:
        where = f"scenes/{scene.id}"
        if not scene.steps:
            warn(where, "Scene has no beats.")
        for step in scene.steps:
            if isinstance(step, Beat):
                check_beat(f"{where}/{step.id}", step)
            else:
                check_split(f"{where}/{step.id}", step)
        ex = scene.exit
        ew = f"{where}/exit"
        if ex.kind == "next":
            if ex.goes_to not in scenes:
                err(ew, f"Next scene '{ex.goes_to}' does not exist.")
        elif ex.kind == "choice":
            check_choice(f"{ew}/choice", ex.choice, set(scenes), "scene")
        elif ex.kind == "variable":
            if not ex.rules:
                err(ew, "A variable exit needs at least one rule.")
            for i, rule in enumerate(ex.rules):
                check_condition(f"{ew}/rules/{i}", rule.when)
                if rule.goes_to not in scenes:
                    err(f"{ew}/rules/{i}", f"Rule leads to unknown scene '{rule.goes_to}'.")
            if ex.otherwise not in scenes:
                err(ew, "A variable exit needs an 'otherwise' scene that exists.")

    for scene in story.scenes:
        check_scene(scene)

    if story.start_scene in scenes:
        reachable = _reachable(story.start_scene, scenes)
        for scene in story.scenes:
            if scene.id not in reachable:
                warn(f"scenes/{scene.id}", "No path leads to this scene.")
        if not any(scenes[s].exit.kind == "end" for s in reachable):
            warn("story", "No reachable scene ends the story.")

    for c in story.characters:
        for p in c.portraits:
            if asset_exists and not asset_exists(p):
                err(f"characters/{c.id}", f"Portrait file '{p}' is missing.")
    for i, note in enumerate(story.memory_seed):
        if note.about is not None and note.about not in characters:
            err(f"memory_seed/{i}", f"Unknown character '{note.about}'.")

    return issues


def scene_targets(scene: Scene) -> list[str]:
    ex = scene.exit
    if ex.kind == "next":
        return [ex.goes_to] if ex.goes_to else []
    if ex.kind == "choice" and ex.choice:
        return [o.goes_to for o in ex.choice.options if o.goes_to]
    if ex.kind == "variable":
        out = [r.goes_to for r in ex.rules]
        return out + ([ex.otherwise] if ex.otherwise else [])
    return []


def _reachable(start: str, scenes: dict[str, Scene]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        sid = stack.pop()
        if sid in seen or sid not in scenes:
            continue
        seen.add(sid)
        stack.extend(scene_targets(scenes[sid]))
    return seen


def _all_inner_ids(story: Story) -> Iterable[str]:
    for scene in story.scenes:
        for step in scene.steps:
            yield step.id
            beats = [step] if isinstance(step, Beat) else []
            if isinstance(step, Split):
                for lane in step.lanes:
                    yield lane.id
                    beats.extend(lane.beats)
            for beat in beats:
                if beat is not step:
                    yield beat.id
                for line in beat.lines:
                    yield line.id


def _duplicates(kind: str, ids: Iterable[str], err: Callable[[str, str], None]) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            err("story", f"Duplicate {kind} id '{i}'.")
        seen.add(i)


def _value_fits(var: StoryVariable, value: object) -> bool:
    if var.type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if var.type == "flag":
        return isinstance(value, bool)
    return isinstance(value, str)
