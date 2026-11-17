import { href, parseRoute } from "./route";
import { moveItem } from "./project/order";
import { fitDuration, estimateSpokenS } from "./project/defaults";

describe("routes", () => {
  it("round-trips project and shot", () => {
    const r = { name: "project" as const, slug: "my film", shot: "shot_1" };
    expect(parseRoute(href(r))).toEqual(r);
    expect(parseRoute("#/project/x")).toEqual({ name: "project", slug: "x", shot: null });
    expect(parseRoute("#/settings")).toEqual({ name: "settings" });
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
