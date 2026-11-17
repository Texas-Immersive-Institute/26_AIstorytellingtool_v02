import { describe, expect, it } from "vitest";
import { MAX_ZOOM, MIN_ZOOM, fitView, nextDetail, wheelFactor, zoomAt } from "./mapView";

describe("beat map view", () => {
  it("keeps the point under the cursor fixed while zooming", () => {
    const view = { x: 40, y: 10, k: 1 };
    const next = zoomAt(view, 0.5, 240, 110);
    // the map point that was at (240, 110) is (200, 100); it must still be on screen at (240, 110)
    expect(200 * next.k + next.x).toBeCloseTo(240);
    expect(100 * next.k + next.y).toBeCloseTo(110);
  });

  it("clamps zoom", () => {
    expect(zoomAt({ x: 0, y: 0, k: 1 }, 100, 0, 0).k).toBe(MAX_ZOOM);
    expect(zoomAt({ x: 0, y: 0, k: 1 }, 0, 0, 0).k).toBe(MIN_ZOOM);
  });

  it("collapses and expands with a gap between the two thresholds", () => {
    expect(nextDetail("full", 0.6)).toBe("full");
    expect(nextDetail("full", 0.5)).toBe("compact");
    expect(nextDetail("compact", 0.6)).toBe("compact");
    expect(nextDetail("compact", 0.7)).toBe("full");
  });

  it("fits wide maps and never zooms past 1", () => {
    const wide = fitView({ w: 4000, h: 600 }, { w: 1000, h: 500 });
    expect(wide.k).toBeCloseTo(952 / 4000);
    expect(fitView({ w: 200, h: 100 }, { w: 1000, h: 500 }).k).toBe(1);
  });

  it("zooms in on wheel up and out on wheel down", () => {
    expect(wheelFactor(-100, 0, false)).toBeGreaterThan(1);
    expect(wheelFactor(100, 0, false)).toBeLessThan(1);
    expect(wheelFactor(3, 1, false)).toBeCloseTo(wheelFactor(48, 0, false));
  });
});
