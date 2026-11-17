import type { RunEvent, RunLine, RunMemory, RunMessage, RunSnapshot, RunWindow } from "./types";

/** Shape of GET /projects/<slug>/playthroughs/<id> (engine.record). */
export interface PlaythroughRecord {
  format: number;
  started_at: string;
  mode: "live" | "outline_only";
  ended: boolean;
  story: SavedStory;
  events: RunEvent[];
  final: {
    variables: Record<string, number | boolean | string | null>;
    memory: RunMemory[];
    live_profiles: Record<string, string[]>;
    path: string[];
  };
}

interface SavedStory {
  title: string;
  characters?: { id: string; name: string; color?: string; portraits?: string[] }[];
  variables?: { name: string; default: number | boolean | string | null }[];
  memory_seed?: { text: string; about?: string | null; pinned?: boolean }[];
  [key: string]: unknown;
}

/** A choice point or influence window as it closed. */
export interface Decision {
  window_id: string;
  kind: "choice" | "influence";
  prompt: string;
  reason: string;
  messages: number;
  chosen_label?: string;
  decided_by?: string;
  totals?: { id: string; label: string; total: number }[];
  top?: { id: string; text: string; weight: number }[];
}

export type ReplayState = RunSnapshot & {
  /** The event this state is "at": everything up to and including it has happened. */
  at: number;
  decision: Decision | null;
};

/**
 * The Debug view's state just after event `at` of a saved playthrough, rebuilt from the story it
 * was played with and its event log. Choice totals are exact only once a window closes: while it
 * is open, the record has the messages but not the running totals.
 */
export function replayAt(record: PlaythroughRecord, slug: string, at: number): ReplayState {
  const story = record.story;
  const characters = new Map((story.characters ?? []).map((c) => [c.id, c]));
  const state: ReplayState = {
    active: false,
    version: 0,
    epoch: 0,
    slug,
    title: story.title,
    mode: record.mode,
    status: "running",
    error: null,
    elapsed: 0,
    scene: { id: null, title: null },
    beat_id: null,
    lane_id: null,
    picture: null,
    audio: null,
    line: null,
    wait: null,
    window: null,
    variables: Object.fromEntries((story.variables ?? []).map((v) => [v.name, v.default])),
    memory: (story.memory_seed ?? []).map((n, i) => ({
      id: `seed_${i + 1}`,
      text: n.text,
      about: n.about ?? null,
      pinned: !!n.pinned,
      source: "seed" as const,
    })),
    live_profiles: Object.fromEntries((story.characters ?? []).map((c) => [c.id, [] as string[]])),
    path: [],
    has_audience_input: false,
    ai: { enabled: false, label: null, pending: null },
    matcher: "",
    messages: [],
    events: [],
    at,
    decision: null,
  };
  const messages = new Map<string, RunMessage>();
  const events = record.events.slice(0, Math.max(0, at + 1));

  for (const e of events) {
    state.elapsed = e.t;
    switch (e.type) {
      case "started":
        state.ai = { enabled: !!e.ai, label: (e.ai as string | null) ?? null, pending: null };
        state.matcher = String(e.matcher ?? "");
        break;
      case "scene_entered":
        state.scene = { id: String(e.scene_id), title: String(e.title ?? e.scene_id) };
        state.lane_id = null;
        state.path = [...(state.path ?? []), String(e.scene_id)];
        break;
      case "beat_entered":
        state.beat_id = String(e.beat_id);
        state.picture = (e.picture as string | null) ?? null;
        state.audio = (e.audio as string | null) ?? null;
        state.line = null;
        break;
      case "lane_picked":
        state.lane_id = String(e.lane_id);
        break;
      case "line_shown": {
        const speaker = characters.get(String(e.speaker ?? ""));
        const authored = findById(story, String(e.line_id)) as { action?: string; kind?: RunLine["kind"] } | null;
        state.line = {
          id: String(e.line_id),
          speaker: speaker?.id ?? null,
          speaker_name: speaker?.name ?? null,
          color: speaker?.color ?? null,
          portrait: speaker?.portraits?.[0] ?? null,
          text: String(e.text ?? ""),
          action: authored?.action ?? "",
          kind: authored?.kind ?? (e.source === "authored" ? "authored" : "ai"),
          source: e.source as RunLine["source"],
        };
        break;
      }
      case "ai_requested":
        state.ai = { ...state.ai!, pending: e.kind as "line" | "fill" };
        break;
      case "ai_answered":
      case "ai_fallback":
        state.ai = { ...state.ai!, pending: null };
        break;
      case "window_opened": {
        const options = (e.options as { id: string; label: string }[] | undefined) ?? [];
        const win: RunWindow = {
          id: String(e.window_id),
          kind: e.kind as RunWindow["kind"],
          prompt: String(e.prompt ?? ""),
          fills_variable: null,
          message_count: 0,
        };
        if (win.kind === "choice") win.options = options.map((o) => ({ ...o, total: 0, messages: 0 }));
        state.window = win;
        state.decision = null;
        break;
      }
      case "window_closed": {
        const totals = e.totals as Record<string, number> | undefined;
        const labels = new Map((state.window?.options ?? []).map((o) => [o.id, o.label]));
        state.decision = {
          window_id: String(e.window_id),
          kind: e.kind as Decision["kind"],
          prompt: state.window?.prompt ?? "",
          reason: String(e.reason ?? ""),
          messages: Number(e.messages ?? 0),
          chosen_label: e.chosen_label as string | undefined,
          decided_by: e.decided_by as string | undefined,
          totals: totals && Object.entries(totals).map(([id, total]) => ({ id, label: labels.get(id) ?? id, total })),
          top: e.top as Decision["top"],
        };
        state.window = null;
        break;
      }
      case "message": {
        const m = { ...(e.message as RunMessage) };
        messages.set(m.id, m);
        state.has_audience_input = true;
        if (state.window && m.window_id === state.window.id) state.window.message_count += 1;
        break;
      }
      case "thumbs_up": {
        const m = messages.get(String(e.message_id));
        if (m) messages.set(m.id, { ...m, thumbs: Number(e.total ?? m.thumbs + 1) });
        break;
      }
      case "message_hidden":
      case "message_shown": {
        const m = messages.get(String(e.message_id));
        if (m) messages.set(m.id, { ...m, hidden: e.type === "message_hidden" });
        break;
      }
      case "variable_changed":
        state.variables = { ...state.variables, [String(e.name)]: e.new as string | number | boolean | null };
        break;
      case "memory_added":
        state.memory = [...(state.memory ?? []), e.entry as RunMemory];
        break;
      case "memory_edited": {
        const entry = e.entry as RunMemory;
        state.memory = (state.memory ?? []).map((m) => (m.id === entry.id ? entry : m));
        break;
      }
      case "memory_deleted":
        state.memory = (state.memory ?? []).filter((m) => m.id !== e.entry_id);
        break;
      case "live_profile_added": {
        const who = String(e.character);
        state.live_profiles = { ...state.live_profiles, [who]: [...(state.live_profiles?.[who] ?? []), String(e.note)] };
        break;
      }
      case "paused":
        state.status = "paused";
        break;
      case "resumed":
        state.status = "running";
        break;
      case "ended":
      case "stopped":
        state.status = "ended";
        state.window = null;
        state.line = null;
        break;
      case "error":
        state.error = String(e.message ?? "");
        break;
    }
  }
  state.messages = [...messages.values()];
  state.events = events;
  return state;
}

/** Where the replay can jump: the next event of one of these types after `from`. */
export function nextOf(events: RunEvent[], from: number, types: string[]): number | null {
  const i = events.findIndex((e, k) => k > from && types.includes(e.type));
  return i < 0 ? null : i;
}

export function previousOf(events: RunEvent[], from: number, types: string[]): number | null {
  for (let k = from - 1; k >= 0; k--) if (types.includes(events[k].type)) return k;
  return null;
}

/** The authored object with this id anywhere in the saved story (lines, beats, …). */
function findById(node: unknown, id: string): Record<string, unknown> | null {
  if (Array.isArray(node)) {
    for (const item of node) {
      const found = findById(item, id);
      if (found) return found;
    }
  } else if (node && typeof node === "object") {
    const obj = node as Record<string, unknown>;
    if (obj.id === id && "text" in obj) return obj;
    for (const value of Object.values(obj)) {
      const found = findById(value, id);
      if (found) return found;
    }
  }
  return null;
}
