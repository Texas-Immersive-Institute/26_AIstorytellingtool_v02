"""The H3 workflow pack: API-format ComfyUI recipes plus pack.json, which binds each stage's
inputs (prompt, references, duration…) to node inputs. Takes fills a recipe in and sends it to
ComfyUI itself (ADR-0006). The pack folder is a copy of the one in comfyui_apitool, and this
module reproduces how that tool fills recipes in, so the same pack works the same way.
"""

from __future__ import annotations

import copy
import json
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PACK_SCHEMA_VERSION = 1
DEFAULT_PACK = Path(__file__).resolve().parents[2] / "workflow_packs" / "h3_seed_hunter"
MEDIA_KINDS = ("picture", "video", "audio")
# The node that pins a picture to a frame of the video (H3 frame guide).
FRAME_GUIDE = "MiniMaxH3AddGuide"


class PackError(ValueError):
    """A stage or input the pack doesn't have, or a value it can't take."""


class Param(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: str  # text, string, number, enum, references, audio, loras, image, boolean
    node_id: str
    input_name: str
    label: str | None = None
    role: str | None = None
    default: Any = None
    locked: bool = False  # fixed by the pack; edits are refused
    required: bool = False
    value_map: dict[str, Any] | None = None
    requires: dict[str, int] | None = None  # references: minimum items per kind
    upload_subfolder: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    enum_options: list[str] | None = None


class Stage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    recipe: str
    params: list[Param] = Field(default_factory=list)

    def param(self, name: str) -> Param:
        found = next((p for p in self.params if p.name == name), None)
        if found is None:
            raise PackError(f"Stage {self.id!r} has no {name!r} input")
        return found


class Pack:
    def __init__(self, folder: Path = DEFAULT_PACK):
        self.folder = folder
        raw = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
        if raw.get("pack_schema_version") != PACK_SCHEMA_VERSION:
            raise PackError(f"Unsupported pack_schema_version {raw.get('pack_schema_version')}")
        self.id: str = raw["id"]
        self.title: str = raw["title"]
        subfolder = raw.get("upload_subfolder")
        self.stages: dict[str, Stage] = {}
        for spec in raw["stages"]:
            stage = Stage.model_validate(spec)
            recipe = self._load_recipe(stage)
            for param in stage.params:
                param.node_id = str(param.node_id)
                if "default" not in param.model_fields_set:
                    param.default = _recipe_default(stage, param, recipe)
                if param.type in ("audio", "references") and subfolder:
                    param.upload_subfolder = param.upload_subfolder or subfolder
            self.stages[stage.id] = stage
        # Built here, not shipped in the pack: a no-picture twin of every first-frame video stage.
        self._built_recipes: dict[str, dict[str, Any]] = {}
        for stage in list(self.stages.values()):
            if stage.id.startswith("video_") and stage.id.endswith("_first"):
                self._add_no_picture_stage(stage)

    def _add_no_picture_stage(self, source: Stage) -> None:
        """`video_*_none`: the `*_first` stage with its frame guide taken out, so the prompt
        alone drives the video (H3's T2VA format). Other references (audio) work as before."""
        spec = source.model_dump()
        spec["id"] = source.id.removesuffix("_first") + "_none"
        spec["title"] = source.title.replace("first frame", "no picture")
        spec["frames"] = "none"
        spec["built_from"] = source.id
        for param in spec["params"]:
            if param["type"] == "references":
                requires = {
                    k: n for k, n in (param.get("requires") or {}).items() if k != "picture"
                }
                param["requires"] = requires or None
                param["required"] = bool(requires)
                param["description"] = "No picture: the prompt alone sets the scene"
        stage = Stage.model_validate(spec)
        recipe = without_frame_guides(self._load_recipe(source))
        for param in stage.params:
            if param.node_id not in recipe:
                raise PackError(f"Stage {stage.id!r}: node {param.node_id} is missing")
        self.stages[stage.id] = stage
        self._built_recipes[stage.id] = recipe

    def _load_recipe(self, stage: Stage) -> dict[str, Any]:
        path = (self.folder / stage.recipe).resolve()
        if self.folder.resolve() not in path.parents:
            raise PackError(f"Stage {stage.id!r} recipe must stay inside the pack folder")
        return json.loads(path.read_text(encoding="utf-8"))

    @cached_property
    def _recipes(self) -> dict[str, dict[str, Any]]:
        return {
            sid: self._built_recipes.get(sid) or self._load_recipe(stage)
            for sid, stage in self.stages.items()
        }

    def stage(self, stage_id: str) -> Stage:
        if stage_id not in self.stages:
            raise PackError(f"The {self.title} pack has no stage {stage_id!r}")
        return self.stages[stage_id]

    def fill(self, stage_id: str, values: dict[str, Any], *, run_id: str) -> dict[str, Any]:
        """The stage's recipe with every bound input set: pack defaults, then `values`.

        References and audio must already be uploaded: `{"kind", "name", "subfolder"}`.
        Locked inputs keep the pack's value; `{run_id}` in them names this run's output folder.
        """
        stage = self.stage(stage_id)
        names = {p.name for p in stage.params}
        unknown = sorted(set(values) - names)
        if unknown:
            raise PackError(f"Stage {stage_id!r} has no input {', '.join(map(repr, unknown))}")
        merged: dict[str, Any] = {}
        for param in stage.params:
            if param.locked:
                if param.name in values and values[param.name] != param.default:
                    raise PackError(f"{param.label or param.name} is fixed by the workflow pack")
                value = param.default
                if isinstance(value, str):
                    value = value.replace("{run_id}", run_id)
            else:
                value = values.get(param.name, param.default)
            if param.required and value in (None, "", []):
                raise PackError(f"Set {param.label or param.name} before generating")
            if param.type == "references":
                short = _missing(value or [], param.requires or {})
                if short:
                    raise PackError(f"{param.label or param.name} needs {'; '.join(short)}")
            merged[param.name] = value

        workflow = copy.deepcopy(self._recipes[stage_id])
        for param in stage.params:
            node = workflow.get(param.node_id)
            if not isinstance(node, dict):
                raise PackError(f"Stage {stage_id!r}: node {param.node_id} is missing")
            inputs = node.setdefault("inputs", {})
            value = merged[param.name]
            if param.value_map is not None:
                if str(value) not in param.value_map:
                    raise PackError(
                        f"{param.label or param.name} must be one of {', '.join(param.value_map)}"
                    )
                _set_input(inputs, param.input_name, param.value_map[str(value)])
            else:
                _set_input(inputs, param.input_name, _coerce(param, value))
        return workflow


# -- recipes built from the pack's own ------------------------------------------------------------


def without_frame_guides(recipe: dict[str, Any]) -> dict[str, Any]:
    """A copy of `recipe` with its frame guides taken out.

    A frame guide takes the conditioning in its `positive` input and passes it on (output 0) with
    a picture pinned to a frame. Whatever read the guide now reads that `positive` input, and the
    guide and the nodes that only fed it (the picture resize) are dropped.
    """
    workflow = copy.deepcopy(recipe)
    guides = [nid for nid, node in workflow.items() if node.get("class_type") == FRAME_GUIDE]
    if not guides:
        raise PackError("The recipe has no frame guide to take out")
    for gid in guides:
        positive = workflow[gid].get("inputs", {}).get("positive")
        if not _is_link(positive):
            raise PackError(f"Frame guide {gid} has no linked 'positive' input")
        for nid, node in workflow.items():
            inputs = node.get("inputs", {})
            for name, value in inputs.items():
                if _is_link(value) and str(value[0]) == gid:
                    if value[1] != 0:
                        raise PackError(f"Node {nid} reads output {value[1]} of frame guide {gid}")
                    inputs[name] = list(positive)
    removed = [workflow.pop(gid) for gid in guides]
    pending = [
        str(v[0]) for node in removed for v in node.get("inputs", {}).values() if _is_link(v)
    ]
    while pending:
        nid = pending.pop()
        if nid in workflow and not _has_readers(workflow, nid):
            node = workflow.pop(nid)
            pending += [str(v[0]) for v in node.get("inputs", {}).values() if _is_link(v)]
    return workflow


def _is_link(value: Any) -> bool:
    """A recipe input that reads another node's output: `[node id, output index]`."""
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


def _has_readers(workflow: dict[str, Any], nid: str) -> bool:
    return any(
        _is_link(v) and str(v[0]) == nid
        for node in workflow.values()
        for v in node.get("inputs", {}).values()
    )


# -- turning values into what the nodes read ------------------------------------------------------


def comfy_input_name(name: str, subfolder: str = "") -> str:
    """How loader nodes name a file in ComfyUI's input folder (`sub/name`)."""
    return f"{subfolder.strip('/')}/{name}" if subfolder else name


def media_state(items: list[dict[str, Any]]) -> str:
    """References as `MiniMaxH3MediaLoader.media_state`: <Picture n>, <Video n>, <Audio n>."""
    state: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        kind = item.get("kind")
        if kind not in MEDIA_KINDS or not item.get("name"):
            raise PackError("Each reference needs a kind and an uploaded file name")
        name = str(item["name"])
        entry: dict[str, Any] = {
            "kind": kind,
            "file": f"{comfy_input_name(name, str(item.get('subfolder') or ''))} [input]",
            "name": PurePosixPath(name).name,
            "uid": f"ref{index}",
        }
        if kind == "video":
            entry["has_audio"] = bool(item.get("has_audio", True))
            entry["audio_mode"] = item.get("audio_mode", "paired")
        else:
            entry["has_audio"] = kind == "audio"
            entry["audio_mode"] = "off"
        state.append(entry)
    return json.dumps(state, separators=(",", ":"))


def normalize_loras(value: Any) -> list[dict[str, Any]]:
    """`[{name, strength?, on?}]`, or the Pixaroma state a recipe stores."""
    if value in (None, ""):
        return []
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict):
        value = [
            {"name": lora.get("name"), "strength": lora.get("sm", 1), "on": lora.get("on", True)}
            for lora in value.get("loras") or []
        ]
    loras = []
    for raw in value:
        raw = {"name": raw} if isinstance(raw, str) else raw
        if not isinstance(raw, dict) or not raw.get("name"):
            raise PackError("Each LoRA needs a name")
        loras.append(
            {
                "name": raw["name"],
                "strength": raw.get("strength", 1),
                "on": raw.get("on", True) is not False,
            }
        )
    return loras


def pixaroma_state(loras: list[dict[str, Any]]) -> str:
    return json.dumps(
        {
            "version": 1,
            "sep": ", ",
            "cacheMode": "last",
            "loras": [
                {
                    "name": lora["name"],
                    "on": lora["on"],
                    "sm": lora["strength"],
                    "sc": lora["strength"],
                    "triggers": [],
                }
                for lora in loras
            ],
        },
        separators=(",", ":"),
    )


def _coerce(param: Param, value: Any) -> Any:
    if param.type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise PackError(f"{param.label or param.name} must be a number")
        num = float(value)
        if param.step and param.step > 0:
            base = param.min_value or 0.0
            num = round((num - base) / param.step) * param.step + base
            num = round(num, 6)  # keep 5.17 as 5.17, not 5.170000000000001
        if param.min_value is not None:
            num = max(num, param.min_value)
        if param.max_value is not None:
            num = min(num, param.max_value)
        return int(num) if num.is_integer() else num
    if param.type == "boolean":
        return bool(value)
    if param.type == "references":
        return media_state(value or [])
    if param.type == "loras":
        return pixaroma_state(normalize_loras(value))
    if param.type == "audio":
        if not value:
            return None
        if isinstance(value, dict):
            return comfy_input_name(str(value["name"]), str(value.get("subfolder") or ""))
        return str(value)
    if param.type in ("text", "string", "enum"):
        if value is None:
            return None
        text = str(value)
        return "None" if param.role == "lora" and not text.strip() else text
    return value


def _set_input(inputs: dict[str, Any], path: str, value: Any) -> None:
    if path in inputs:  # ComfyUI dynamic inputs such as "mode.megapixels" are literal keys
        inputs[path] = value
        return
    *parents, last = path.split(".")
    cur = inputs
    for part in parents:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = cur[part] = {}
        cur = nxt
    cur[last] = value


def _recipe_default(stage: Stage, param: Param, recipe: dict[str, Any]) -> Any:
    node = recipe.get(param.node_id)
    if not isinstance(node, dict):
        raise PackError(f"Stage {stage.id!r} input {param.name!r} binds missing node")
    inputs = node.get("inputs", {})
    if param.input_name in inputs:
        current = inputs[param.input_name]
    else:
        current = inputs
        for part in param.input_name.split("."):
            if not isinstance(current, dict) or part not in current:
                raise PackError(f"Stage {stage.id!r} input {param.name!r} binds missing input")
            current = current[part]
    if param.type == "references":
        return []
    if param.type == "loras":
        return normalize_loras(current)
    if isinstance(current, list):  # a link to another node, not a value
        raise PackError(f"Stage {stage.id!r} input {param.name!r} binds a linked input")
    if param.type == "audio":
        return current or None
    return current


def _missing(items: list[dict[str, Any]], requires: dict[str, int]) -> list[str]:
    counts = dict.fromkeys(MEDIA_KINDS, 0)
    for item in items:
        counts[item.get("kind", "")] = counts.get(item.get("kind", ""), 0) + 1
    return [
        f"{need} {kind}{'s' if need > 1 else ''} (has {counts.get(kind, 0)})"
        for kind, need in requires.items()
        if counts.get(kind, 0) < need
    ]
