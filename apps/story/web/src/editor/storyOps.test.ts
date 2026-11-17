import type { Story } from "../generated/story";
import { addScene, allIds, connect, deleteScene, idMaker, newSplit, renameVariable, sceneLinks, unlink } from "./storyOps";

function story(): Story {
  return {
    schema_version: 1,
    title: "t",
    description: "",
    start_scene: null,
    settings: { stage_style: "visual_novel", reading_chars_per_s: 15, min_beat_s: 2.5, thumbs_up_factor: 1, match_threshold: 0.35 },
    characters: [],
    variables: [{ name: "trust", type: "number", default: 1, description: "" }],
    memory_seed: [],
    scenes: [],
  };
}

test("adding scenes sets the start and gives unique ids", () => {
  const s = story();
  const a = addScene(s, 0, 0);
  const b = addScene(s, 100, 0);
  expect(a).toBe("new_scene");
  expect(b).toBe("new_scene_2");
  expect(s.start_scene).toBe(a);
});

test("connect grows next into a choice, then adds options", () => {
  const s = story();
  const a = addScene(s, 0, 0, "A");
  const b = addScene(s, 0, 0, "B");
  const c = addScene(s, 0, 0, "C");
  const d = addScene(s, 0, 0, "D");
  connect(s, a, b);
  expect(s.scenes[0].exit).toMatchObject({ kind: "next", goes_to: b });
  connect(s, a, c);
  expect(s.scenes[0].exit.kind).toBe("choice");
  expect(s.scenes[0].exit.choice!.options.map((o) => o.goes_to)).toEqual([b, c]);
  connect(s, a, c); // no duplicate
  connect(s, a, d);
  expect(sceneLinks(s).map((l) => l.target)).toEqual([b, c, d]);
});

test("unlink and deleteScene remove paths", () => {
  const s = story();
  const a = addScene(s, 0, 0, "A");
  const b = addScene(s, 0, 0, "B");
  connect(s, a, b);
  unlink(s, `${a}:next`);
  expect(s.scenes[0].exit.kind).toBe("end");
  connect(s, a, b);
  deleteScene(s, b);
  expect(s.scenes[0].exit.kind).toBe("end");
  deleteScene(s, a);
  expect(s.start_scene).toBeNull();
});

test("newSplit makes two lanes with one option each and unique ids", () => {
  const s = story();
  addScene(s, 0, 0, "A");
  const split = newSplit(idMaker(s));
  s.scenes[0].steps.push(split);
  expect(split.lanes).toHaveLength(2);
  expect(split.choice!.options.map((o) => o.goes_to)).toEqual(split.lanes.map((l) => l.id));
  const ids = [...allIds(s)];
  expect(new Set(ids).size).toBe(ids.length);
});

test("renameVariable updates conditions, effects and placeholders", () => {
  const s = story();
  addScene(s, 0, 0, "A");
  const beat = s.scenes[0].steps[0];
  if (beat.kind !== "beat") throw new Error();
  beat.lines[0].text = "Trust is {trust}.";
  beat.effects.push({ variable: "trust", op: "add", value: 1 });
  beat.visible_when = { variable: "trust", op: "ge", value: 2 };
  renameVariable(s, "trust", "faith");
  expect(s.variables[0].name).toBe("faith");
  expect(beat.lines[0].text).toBe("Trust is {faith}.");
  expect(beat.effects[0].variable).toBe("faith");
  expect(beat.visible_when.variable).toBe("faith");
});
