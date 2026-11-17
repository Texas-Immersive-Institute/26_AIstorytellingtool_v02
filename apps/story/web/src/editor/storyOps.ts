/** Pure edits on a Story draft. Each function mutates the draft it is given. */
import type {
  Beat,
  ChoicePoint,
  Condition,
  Effect,
  Lane,
  Line,
  Scene,
  SceneExit,
  Split,
  Story,
  StoryVariable,
} from "../generated/story";

export type Step = Beat | Split;

// --- ids ------------------------------------------------------------------------------

export function allIds(story: Story): Set<string> {
  const ids = new Set<string>();
  for (const scene of story.scenes) {
    ids.add(scene.id);
    for (const step of scene.steps) {
      ids.add(step.id);
      const beats = step.kind === "beat" ? [step] : step.lanes.flatMap((l) => (ids.add(l.id), l.beats));
      for (const beat of beats) {
        ids.add(beat.id);
        beat.lines.forEach((l) => ids.add(l.id));
      }
      const choice = step.kind === "split" ? step.choice : null;
      choice?.options.forEach((o) => ids.add(o.id));
    }
    scene.exit.choice?.options.forEach((o) => ids.add(o.id));
  }
  story.characters.forEach((c) => ids.add(c.id));
  return ids;
}

/** An id maker that never repeats an id in the story or one it already handed out. */
export function idMaker(story: Story): (prefix: string) => string {
  const taken = allIds(story);
  return (prefix) => {
    for (;;) {
      const id = `${prefix}_${Math.random().toString(36).slice(2, 7)}`;
      if (!taken.has(id)) {
        taken.add(id);
        return id;
      }
    }
  };
}

export function newId(story: Story, prefix: string): string {
  return idMaker(story)(prefix);
}

export function slugId(story: Story, text: string, fallback: string): string {
  const base = text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 30) || fallback;
  const taken = allIds(story);
  let id = base;
  for (let n = 2; taken.has(id); n++) id = `${base}_${n}`;
  return id;
}

// --- factories ------------------------------------------------------------------------

export const emptyExit = (): SceneExit => ({ kind: "end", goes_to: null, choice: null, rules: [], otherwise: null });

type MakeId = (prefix: string) => string;

export function newLine(make: MakeId, kind: "authored" | "ai" = "authored", speaker: string | null = null): Line {
  return { id: make("line"), speaker, kind, text: "", intent: "", action: "" };
}

export function newBeat(make: MakeId): Beat {
  return {
    kind: "beat",
    id: make("beat"),
    title: "",
    picture: { mode: "hold", asset: null },
    audio: { mode: "hold", asset: null },
    lines: [newLine(make)],
    influence: null,
    duration_s: null,
    visible_when: null,
    effects: [],
  };
}

export function newChoice(): ChoicePoint {
  return { prompt: "", options: [], countdown_s: 30 };
}

export function newLane(make: MakeId, label: string): Lane {
  return { id: make("lane"), label, beats: [newBeat(make)] };
}

export function newSplit(make: MakeId): Split {
  const lanes = [newLane(make, "Lane A"), newLane(make, "Lane B")];
  return {
    kind: "split",
    id: make("split"),
    picked_by: "choice",
    choice: {
      ...newChoice(),
      options: lanes.map((lane, i) => ({
        id: make("opt"),
        label: `Option ${"AB"[i]}`,
        meaning: "",
        goes_to: lane.id,
        effects: [],
      })),
    },
    rules: [],
    otherwise: null,
    lanes,
  };
}

export function newCondition(story: Story): Condition {
  const v = story.variables[0];
  return { variable: v?.name ?? "", op: v ? defaultOp(v) : "eq", value: v ? defaultValue(v) : null };
}

export function newEffect(story: Story): Effect {
  const v = story.variables[0];
  return { variable: v?.name ?? "", op: v?.type === "number" ? "add" : "set", value: v ? defaultValue(v) : null };
}

export function defaultOp(v: StoryVariable): Condition["op"] {
  return v.type === "number" ? "ge" : v.type === "flag" ? "eq" : "is_set";
}

export function defaultValue(v: StoryVariable): number | boolean | string | null {
  return v.type === "number" ? 1 : v.type === "flag" ? true : null;
}

// --- scenes ---------------------------------------------------------------------------

export function addScene(story: Story, x: number, y: number, title = "New scene", id = slugId(story, title, "scene")): string {
  const scene: Scene = { id, title, summary: "", position: { x, y }, steps: [], exit: emptyExit() };
  scene.steps.push(newBeat(idMaker(story)));
  story.scenes.push(scene);
  if (!story.start_scene) story.start_scene = id;
  return id;
}

/** Remove a scene and every link pointing at it. */
export function deleteScene(story: Story, id: string): void {
  story.scenes = story.scenes.filter((s) => s.id !== id);
  for (const s of story.scenes) unlinkTarget(s.exit, id);
  if (story.start_scene === id) story.start_scene = story.scenes[0]?.id ?? null;
}

function unlinkTarget(exit: SceneExit, target: string) {
  if (exit.goes_to === target) {
    exit.goes_to = null;
    if (exit.kind === "next") exit.kind = "end";
  }
  exit.choice?.options.forEach((o) => {
    if (o.goes_to === target) o.goes_to = null;
  });
  exit.rules = exit.rules.filter((r) => r.goes_to !== target);
  if (exit.otherwise === target) exit.otherwise = null;
}

export interface SceneLink {
  id: string; // stable edge id
  source: string;
  target: string;
  label: string;
}

export function sceneLinks(story: Story): SceneLink[] {
  const out: SceneLink[] = [];
  const known = new Set(story.scenes.map((s) => s.id));
  for (const s of story.scenes) {
    const ex = s.exit;
    const push = (id: string, target: string | null | undefined, label: string) => {
      if (target && known.has(target)) out.push({ id: `${s.id}:${id}`, source: s.id, target, label });
    };
    if (ex.kind === "next") push("next", ex.goes_to, "");
    if (ex.kind === "choice") ex.choice?.options.forEach((o) => push(`opt:${o.id}`, o.goes_to, o.label));
    if (ex.kind === "variable") {
      ex.rules.forEach((r, i) => push(`rule:${i}`, r.goes_to, conditionText(r.when)));
      push("otherwise", ex.otherwise, "otherwise");
    }
  }
  return out;
}

/** Remove one link drawn by sceneLinks. */
export function unlink(story: Story, linkId: string): void {
  const [sceneId, kind, rest] = linkId.split(":");
  const scene = story.scenes.find((s) => s.id === sceneId);
  if (!scene) return;
  const ex = scene.exit;
  if (kind === "next") {
    ex.kind = "end";
    ex.goes_to = null;
  } else if (kind === "opt") {
    const opt = ex.choice?.options.find((o) => o.id === rest);
    if (opt) opt.goes_to = null;
  } else if (kind === "rule") {
    ex.rules.splice(Number(rest), 1);
  } else if (kind === "otherwise") {
    ex.otherwise = null;
  }
}

/** Draw a path from one scene to another, growing the exit as needed. */
export function connect(story: Story, sourceId: string, targetId: string): void {
  const source = story.scenes.find((s) => s.id === sourceId);
  const target = story.scenes.find((s) => s.id === targetId);
  if (!source || !target) return;
  const ex = source.exit;
  if (ex.kind === "end") {
    ex.kind = "next";
    ex.goes_to = targetId;
  } else if (ex.kind === "next") {
    if (ex.goes_to === targetId) return;
    const previous = story.scenes.find((s) => s.id === ex.goes_to);
    ex.kind = "choice";
    ex.choice = newChoice();
    if (previous) ex.choice.options.push(option(story, previous));
    ex.choice.options.push(option(story, target));
    ex.goes_to = null;
  } else if (ex.kind === "choice") {
    ex.choice ??= newChoice();
    if (ex.choice.options.some((o) => o.goes_to === targetId)) return;
    const empty = ex.choice.options.find((o) => !o.goes_to);
    if (empty) empty.goes_to = targetId;
    else ex.choice.options.push(option(story, target));
  } else {
    if (!ex.otherwise) ex.otherwise = targetId;
    else ex.rules.push({ when: newCondition(story), goes_to: targetId });
  }
}

function option(story: Story, target: Scene) {
  return { id: newId(story, "opt"), label: target.title, meaning: "", goes_to: target.id, effects: [] };
}

// --- steps ----------------------------------------------------------------------------

export function moveItem<T>(list: T[], index: number, delta: number): void {
  const to = index + delta;
  if (to < 0 || to >= list.length) return;
  const [item] = list.splice(index, 1);
  list.splice(to, 0, item);
}

export function findScene(story: Story, id: string | null): Scene | undefined {
  return story.scenes.find((s) => s.id === id);
}

// --- variables ------------------------------------------------------------------------

/** Rename a variable everywhere it is used, including {placeholders} in lines. */
export function renameVariable(story: Story, from: string, to: string): void {
  const v = story.variables.find((x) => x.name === from);
  if (!v || from === to) return;
  v.name = to;
  const fixCond = (c: Condition | null | undefined) => {
    if (c && c.variable === from) c.variable = to;
  };
  const fixEffects = (effects: Effect[]) => effects.forEach((e) => e.variable === from && (e.variable = to));
  const fixChoice = (c: ChoicePoint | null | undefined) => c?.options.forEach((o) => fixEffects(o.effects));
  const placeholder = new RegExp(`\\{${from}\\}`, "g");
  const fixBeat = (b: Beat) => {
    fixCond(b.visible_when);
    fixEffects(b.effects);
    if (b.influence?.fills_variable === from) b.influence.fills_variable = to;
    b.lines.forEach((l) => (l.text = l.text.replace(placeholder, `{${to}}`)));
  };
  for (const s of story.scenes) {
    for (const step of s.steps) {
      if (step.kind === "beat") fixBeat(step);
      else {
        fixChoice(step.choice);
        step.rules.forEach((r) => fixCond(r.when));
        step.lanes.forEach((l) => l.beats.forEach(fixBeat));
      }
    }
    fixChoice(s.exit.choice);
    s.exit.rules.forEach((r) => fixCond(r.when));
  }
}

export function conditionText(c: Condition): string {
  const ops: Record<string, string> = { eq: "=", ne: "≠", lt: "<", le: "≤", gt: ">", ge: "≥" };
  if (c.op === "is_set") return `${c.variable} is set`;
  if (c.op === "not_set") return `${c.variable} not set`;
  if (c.op === "contains") return `${c.variable} contains ${JSON.stringify(c.value)}`;
  return `${c.variable} ${ops[c.op] ?? c.op} ${JSON.stringify(c.value)}`;
}
