import type { Story } from "./generated/story";
import type { PlaythroughSummary, RunMemory, RunMessage, RunSnapshot } from "./run/types";

export type { Story };

export interface Issue {
  level: "error" | "warning";
  where: string;
  message: string;
}

export interface SettingsOut {
  projects_dir: string | null;
  suggested_projects_dir: string;
  port: number;
}

export interface ProjectSummary {
  slug: string;
  title: string;
  description: string;
  scene_count: number;
  updated_at: string;
}

export interface ExampleOut {
  name: string;
  title: string;
  description: string;
}

export interface ProjectOut {
  slug: string;
  story: Story;
  issues: Issue[];
}

export interface AssetInfo {
  path: string;
  kind: "picture" | "video" | "audio";
  size: number;
}

export type BackendChoice = "auto" | "ollama" | "claude_cli" | "codex_cli" | "none";

export interface AiSettings {
  backend: BackendChoice;
  ollama_url: string;
  ollama_model: string;
  claude_model: string;
  codex_model: string;
  timeout_s: number;
}

export interface AiStatus {
  setting: BackendChoice;
  backends: { backend: string; label: string; ok: boolean; detail: string }[];
  chosen: string | null;
  reason: string;
}

export interface MatchingStatus {
  matcher: "embeddings" | "word overlap";
  model: string | null;
  ready: boolean;
  downloading: boolean;
  detail: string;
  size_mb?: number;
}

export interface LanInfo {
  listening: boolean;
  urls: string[];
  hint: string | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    let code: string | undefined;
    try {
      const body = await res.json();
      code = body.code;
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail, code);
  }
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function upload(file: File): RequestInit {
  const form = new FormData();
  form.append("file", file);
  return { method: "POST", body: form };
}

export const api = {
  whoami: () => request<{ is_host: boolean }>("/whoami"),
  settings: () => request<SettingsOut>("/settings"),
  saveSettings: (projects_dir: string) => request<SettingsOut>("/settings", json("PUT", { projects_dir })),
  projects: () => request<ProjectSummary[]>("/projects"),
  createProject: (title: string) => request<{ slug: string }>("/projects", json("POST", { title })),
  importProject: (file: File) => request<{ slug: string }>("/projects/import", upload(file)),
  examples: () => request<ExampleOut[]>("/examples"),
  copyExample: (name: string) => request<{ slug: string }>(`/examples/${encodeURIComponent(name)}/copy`, { method: "POST" }),
  project: (slug: string) => request<ProjectOut>(`/projects/${encodeURIComponent(slug)}`),
  saveProject: (slug: string, story: Story) =>
    request<{ issues: Issue[] }>(`/projects/${encodeURIComponent(slug)}`, json("PUT", story)),
  assets: (slug: string) => request<AssetInfo[]>(`/projects/${encodeURIComponent(slug)}/assets`),
  uploadAsset: (slug: string, file: File) =>
    request<AssetInfo>(`/projects/${encodeURIComponent(slug)}/assets`, upload(file)),

  // playthroughs
  startRun: (slug: string, mode: "live" | "outline_only") =>
    request<RunSnapshot>(`/projects/${encodeURIComponent(slug)}/playthroughs`, json("POST", { mode })),
  playthroughs: (slug: string) => request<PlaythroughSummary[]>(`/projects/${encodeURIComponent(slug)}/playthroughs`),
  run: () => request<RunSnapshot>("/run"),
  stopRun: () => request<RunSnapshot>("/run/stop", { method: "POST" }),
  control: (action: string, extra: { seconds?: number; option_id?: string } = {}) =>
    request<RunSnapshot & { ok: boolean }>("/run/control", json("POST", { action, ...extra })),
  say: (author: string, text: string) => request<RunMessage>("/run/messages", json("POST", { author, text })),
  thumbsUp: (id: string, voter: string) =>
    request<{ ok: boolean }>(`/run/messages/${encodeURIComponent(id)}/thumbs`, json("POST", { voter })),
  hideMessage: (id: string, hidden: boolean) =>
    request<{ ok: boolean }>(`/run/messages/${encodeURIComponent(id)}/hidden`, json("POST", { hidden })),
  addMemory: (text: string) => request<RunMemory>("/run/memory", json("POST", { text })),
  editMemory: (id: string, patch: { text?: string; pinned?: boolean }) =>
    request<{ ok: boolean }>(`/run/memory/${encodeURIComponent(id)}`, json("PATCH", patch)),
  deleteMemory: (id: string) => request<{ ok: boolean }>(`/run/memory/${encodeURIComponent(id)}`, { method: "DELETE" }),
  tune: (values: { thumbs_up_factor?: number; match_threshold?: number }) =>
    request<RunSnapshot & { ok: boolean }>("/run/control", json("POST", { action: "tune", ...values })),

  // AI, matching, LAN
  aiSettings: () => request<AiSettings>("/settings/ai"),
  saveAiSettings: (s: AiSettings) => request<AiSettings>("/settings/ai", json("PUT", s)),
  aiStatus: () => request<AiStatus>("/ai/status"),
  aiTest: () =>
    request<{ ok: boolean; backend?: string; seconds?: number; answer?: Record<string, unknown>; detail?: string }>("/ai/test", {
      method: "POST",
    }),
  matchingStatus: () => request<MatchingStatus>("/matching/status"),
  downloadMatching: () => request<MatchingStatus>("/matching/download", { method: "POST" }),
  lan: () => request<LanInfo>("/lan"),

  // audience chat (works from any LAN device)
  chatSend: (participant: string, name: string, text: string) =>
    request<{ id: string }>("/chat/messages", json("POST", { participant, name, text })),
  chatThumbs: (id: string, participant: string) =>
    request<{ ok: boolean }>(`/chat/messages/${encodeURIComponent(id)}/thumbs`, json("POST", { participant })),
};

export const qrUrl = "/api/v1/lan/qr.svg";

export const fileUrl = (slug: string, rel: string) =>
  `/api/v1/projects/${encodeURIComponent(slug)}/files/${rel.split("/").map(encodeURIComponent).join("/")}`;

export const exportUrl = (slug: string) => `/api/v1/projects/${encodeURIComponent(slug)}/export`;
