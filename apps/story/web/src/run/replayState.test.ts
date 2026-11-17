import { nextOf, previousOf, replayAt, type PlaythroughRecord } from "./replayState";
import type { RunEvent } from "./types";

const ev = (seq: number, t: number, type: string, data: Record<string, unknown> = {}): RunEvent => ({ seq, t, type, ...data });

const record: PlaythroughRecord = {
  format: 1,
  started_at: "2026-11-17T10:00:00+00:00",
  mode: "live",
  ended: true,
  story: {
    title: "Lighthouse",
    characters: [{ id: "mara", name: "Mara", color: "#c84", portraits: ["mara.png"] }],
    variables: [{ name: "courage", default: 0 }],
    memory_seed: [{ text: "The lamp has been dark for a week." }],
    scenes: [{ id: "s1", steps: [{ id: "b1", lines: [{ id: "l1", text: "Who's there?", action: "turns", kind: "authored" }] }] }],
  },
  events: [
    ev(1, 0, "started", { mode: "live", ai: "Codex CLI", matcher: "embeddings" }),
    ev(2, 0, "scene_entered", { scene_id: "s1", title: "The tower" }),
    ev(3, 0.1, "beat_entered", { beat_id: "b1", picture: "tower.png", audio: null }),
    ev(4, 0.1, "line_shown", { beat_id: "b1", line_id: "l1", text: "Who's there?", source: "authored", speaker: "mara" }),
    ev(5, 3, "window_opened", { window_id: "w1", kind: "choice", prompt: "Open the door?", seconds: 20, options: [{ id: "o_yes", label: "Yes" }, { id: "o_no", label: "No" }] }),
    ev(6, 5, "message", { message: { id: "m1", author: "ana", author_id: "d1", text: "open it", t: 5, window_id: "w1", from_operator: false, hidden: false, thumbs: 0, scores: { o_yes: 0.8 } } }),
    ev(7, 6, "thumbs_up", { message_id: "m1", voter: "d2", total: 1 }),
    ev(8, 9, "window_closed", { window_id: "w1", kind: "choice", reason: "time", messages: 1, totals: { o_yes: 1.6, o_no: 0 }, chosen: "o_yes", chosen_label: "Yes", decided_by: "audience" }),
    ev(9, 9, "variable_changed", { name: "courage", old: 0, new: 1, cause: "choice" }),
    ev(10, 9.5, "memory_added", { entry: { id: "mem_1", text: "They opened the door.", about: null, pinned: false, source: "ai" } }),
    ev(11, 12, "ended", { path: ["s1"] }),
  ],
  final: { variables: { courage: 1 }, memory: [], live_profiles: {}, path: ["s1"] },
};

test("rebuilds the Debug state at any event", () => {
  const start = replayAt(record, "light", 0);
  expect(start.variables).toEqual({ courage: 0 });
  expect(start.memory?.map((m) => m.source)).toEqual(["seed"]);
  expect(start.ai).toMatchObject({ enabled: true, label: "Codex CLI" });

  const line = replayAt(record, "light", 3);
  expect(line.scene).toEqual({ id: "s1", title: "The tower" });
  expect(line.picture).toBe("tower.png");
  expect(line.line).toMatchObject({ speaker_name: "Mara", portrait: "mara.png", action: "turns", text: "Who's there?" });

  const voting = replayAt(record, "light", 6);
  expect(voting.window?.options?.map((o) => o.label)).toEqual(["Yes", "No"]);
  expect(voting.window?.message_count).toBe(1);
  expect(voting.messages?.[0].thumbs).toBe(1);

  const decided = replayAt(record, "light", 7);
  expect(decided.window).toBeNull();
  expect(decided.decision).toMatchObject({ chosen_label: "Yes", decided_by: "audience" });
  expect(decided.decision?.totals).toEqual([
    { id: "o_yes", label: "Yes", total: 1.6 },
    { id: "o_no", label: "No", total: 0 },
  ]);

  const end = replayAt(record, "light", record.events.length - 1);
  expect(end.status).toBe("ended");
  expect(end.variables).toEqual(record.final.variables);
  expect(end.memory).toHaveLength(2);
  expect(end.path).toEqual(record.final.path);
});

test("jumps to the next or previous event of a kind", () => {
  expect(nextOf(record.events, 0, ["window_opened"])).toBe(4);
  expect(nextOf(record.events, 4, ["window_opened"])).toBeNull();
  expect(previousOf(record.events, 8, ["scene_entered"])).toBe(1);
});
