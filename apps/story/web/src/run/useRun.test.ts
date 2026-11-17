import { newer } from "./useRun";
import type { RunSnapshot } from "./types";

const snap = (epoch: number, version: number): RunSnapshot => ({ active: true, epoch, version });

test("a stale update never replaces a newer snapshot", () => {
  const current = snap(1, 5);
  expect(newer(current, snap(1, 3))).toBe(current);
  const next = snap(1, 6);
  expect(newer(current, next)).toBe(next);
});

test("a server restart (new epoch) is always accepted", () => {
  const restarted = snap(2, 0);
  expect(newer(snap(1, 9), restarted)).toBe(restarted);
  expect(newer(null, restarted)).toBe(restarted);
});
