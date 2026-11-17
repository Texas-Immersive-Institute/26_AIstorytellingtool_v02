import type { Scene } from "../generated/story";
import { scenePicture } from "./SceneGraph";
import { idMaker, newBeat, newSplit } from "./storyOps";

const make = idMaker({ scenes: [], characters: [] } as never);

function scene(): Scene {
  return { id: "s", title: "S", summary: "", position: { x: 0, y: 0 }, steps: [], exit: { kind: "end", goes_to: null, choice: null, rules: [], otherwise: null } };
}

test("a scene's picture is the first picture its beats set", () => {
  const s = scene();
  expect(scenePicture(s)).toBeNull();
  const first = newBeat(make);
  const second = newBeat(make);
  second.picture = { mode: "set", asset: "assets/a.png" };
  s.steps.push(first, second);
  expect(scenePicture(s)).toBe("assets/a.png");
});

test("a picture inside the first lane of a split counts", () => {
  const s = scene();
  const split = newSplit(make);
  split.lanes[0].beats[0].picture = { mode: "set", asset: "assets/lane.png" };
  s.steps.push(split);
  expect(scenePicture(s)).toBe("assets/lane.png");
});
