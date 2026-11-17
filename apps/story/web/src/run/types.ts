/** Shape of GET /api/v1/run (engine.snapshot plus runner fields). */
export interface RunLine {
  id: string;
  speaker: string | null;
  speaker_name: string | null;
  color: string | null;
  portrait: string | null;
  text: string;
  action: string;
  kind: "authored" | "ai";
  source: "authored" | "default" | "ai";
}

export interface RunMessage {
  id: string;
  author: string;
  author_id: string | null;
  text: string;
  t: number;
  window_id: string | null;
  from_operator: boolean;
  hidden: boolean;
  thumbs: number;
  scores: Record<string, number>;
}

export interface RunWindow {
  id: string;
  kind: "choice" | "influence";
  prompt: string;
  fills_variable: string | null;
  message_count: number;
  options?: { id: string; label: string; total: number; messages: number }[];
  unmatched?: number;
  top?: { id: string; text: string; weight: number }[];
}

export interface RunMemory {
  id: string;
  text: string;
  about: string | null;
  pinned: boolean;
  source: "seed" | "operator" | "ai";
}

export interface RunEvent {
  seq: number;
  t: number;
  type: string;
  [key: string]: unknown;
}

export interface RunSnapshot {
  active: boolean;
  version: number;
  epoch: number;
  slug?: string;
  playthrough_id?: string;
  title?: string;
  mode?: "live" | "outline_only";
  status?: "running" | "paused" | "ended";
  error?: string | null;
  elapsed?: number;
  scene?: { id: string | null; title: string | null };
  beat_id?: string | null;
  lane_id?: string | null;
  picture?: string | null;
  audio?: string | null;
  line?: RunLine | null;
  wait?: { kind: "line" | "hold" | "window" | "ai"; remaining: number; length: number } | null;
  window?: RunWindow | null;
  variables?: Record<string, number | boolean | string | null>;
  memory?: RunMemory[];
  live_profiles?: Record<string, string[]>;
  path?: string[];
  has_audience_input?: boolean;
  ai?: { enabled: boolean; label: string | null; pending: "line" | "fill" | null; reason?: string };
  matcher?: string;
  tuning?: { thumbs_up_factor: number; match_threshold: number };
  messages?: RunMessage[];
  events?: RunEvent[];
}

export interface PlaythroughSummary {
  id: string;
  started_at: string;
  mode: string;
  ended: boolean;
  path: string[];
  messages: number;
}

/** Shape of GET /api/v1/chat/state: what audience devices may see. */
export interface ChatState {
  active: boolean;
  epoch: number;
  version: number;
  title?: string;
  status?: "running" | "paused" | "ended";
  scene_title?: string | null;
  line?: { speaker_name: string | null; text: string } | null;
  window?: { id: string; kind: "choice" | "influence"; prompt: string; options: { id: string; label: string }[]; remaining: number | null } | null;
  messages?: { id: string; author: string; author_id: string | null; text: string; thumbs: number }[];
}
