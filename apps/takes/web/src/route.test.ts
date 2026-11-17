import { href, parseRoute } from "./route";
import { moveItem } from "./project/order";
import { fitDuration, estimateSpokenS, progressLabel, sequenceOf } from "./project/defaults";
import type { Shot, Take } from "./api";

describe("routes", () => {
  it("round-trips project and shot", () => {
    const r = { name: "project" as const, slug: "my film", shot: "shot_1" };
    expect(parseRoute(href(r))).toEqual(r);
    expect(parseRoute("#/project/x")).toEqual({ name: "project", slug: "x", shot: null });
    expect(parseRoute("#/settings")).toEqual({ name: "settings" });
    expect(parseRoute(href({ name: "sequence", slug: "my film" }))).toEqual({ name: "sequence", slug: "my film" });
    expect(parseRoute("")).toEqual({ name: "projects" });
  });
});

describe("moveItem", () => {
  it("moves before the drop index", () => {
    expect(moveItem(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "a", "c", "d"]);
    expect(moveItem(["a", "b", "c", "d"], 3, 0)).toEqual(["d", "a", "b", "c"]);
    expect(moveItem(["a", "b", "c", "d"], 1, 4)).toEqual(["a", "c", "d", "b"]);
    expect(moveItem(["a", "b", "c"], 1, 1)).toEqual(["a", "b", "c"]);
  });
});

describe("lengths", () => {
  it("matches the server's H3 lengths", () => {
    const d = [5.17, 5.88, 6.58, 7.29, 8.0];
    expect(fitDuration(5.18, d)).toBe(5.88);
    expect(fitDuration(2, d)).toBe(5.17);
    expect(fitDuration(99, d)).toBe(8.0);
    expect(estimateSpokenS("one two three four five six seven eight nine ten")).toBeCloseTo(4.3, 1);
  });
});

describe("sequenceOf", () => {
  const take = (id: string, status: Take["status"], extra: Partial<Take> = {}) =>
    ({ id, status, duration_s: 6.58, play_from_s: null, ...extra }) as Take;
  const shot = (id: string, takes: Take[], selected: string | null) =>
    ({ id, title: id, notes: "", takes, selected_take: selected }) as Shot;

  it("plays each shot's finished selected take, from its in-point", () => {
    const out = sequenceOf([
      shot("a", [take("a1", "done"), take("a2", "done")], "a2"),
      shot("b", [take("b1", "rendering")], null),
      shot("c", [take("c1", "done", { duration_s: 12.25, play_from_s: 5.17 })], "c1"),
    ]);
    expect(out.map((e) => [e.number, e.take?.id ?? null, e.from_s])).toEqual([
      [1, "a2", 0],
      [2, null, 0],
      [3, "c1", 5.17],
    ]);
    expect(out[2].length_s).toBeCloseTo(7.08, 2);
  });
});

describe("progressLabel", () => {
  it("names what ComfyUI is doing", () => {
    expect(progressLabel({ node: "SamplerCustomAdvanced", step: 4, steps: 6 })).toBe("Sampling · step 4 of 6");
    expect(progressLabel({ node: "VAEDecode", step: 1, steps: 1 })).toBe("Decoding");
    expect(progressLabel({ node: "RIFE VFI", step: null, steps: null })).toBe("Smoothing to 48 fps");
    expect(progressLabel({ node: "MiniMaxH3ReferenceToVideo", step: null, steps: null })).toBe("MiniMaxH3ReferenceToVideo");
  });
});
