// Types mirror apps/takes/src/takes_app (api.py, store.py, stages.py, comfyui.py).

export type Frames = "none" | "first" | "last" | "firstlast";
export type Audio = "native" | "clip" | "voice";
export type TakeStatus =
  | "queued"
  | "preparing"
  | "voicing"
  | "rendering"
  | "downloading"
  | "done"
  | "failed"
  | "cancelled";

export const UNFINISHED: TakeStatus[] = ["queued", "preparing", "voicing", "rendering", "downloading"];

export interface SettingsOut {
  projects_dir: string | null;
  suggested_projects_dir: string;
  comfyui_url: string | null;
  default_comfyui_url: string;
}

export interface ComfyStatus {
  url: string;
  reachable: boolean;
  h3_nodes: boolean;
  ready: boolean;
  manual: boolean;
  version: string | null;
  gpus: string[];
  message: string;
}

export interface Options {
  frames: Frames[];
  audio: Audio[];
  aspect_ratios: string[];
  durations: number[];
}

export interface VoiceReference {
  clip: string;
  line: string;
  tone: string;
  spoken_s?: number | null;
  clip_start_s?: number | null;
  clip_length_s?: number | null;
}

export interface GenerateRequest {
  prompt: string;
  frames: Frames;
  audio: Audio;
  upscale: boolean;
  pictures: string[];
  audio_clip: string | null;
  voice: VoiceReference | null;
  duration_s: number;
  aspect_ratio: string;
  seed: number | null;
}

export interface TakeFile {
  name: string;
  size: number;
  main: boolean;
}

export interface Take {
  id: string;
  request: GenerateRequest;
  stage: string;
  status: TakeStatus;
  seed: number | null;
  upscaled: boolean;
  source_take: string | null;
  voice_audio: string | null;
  duration_s: number | null;
  prompt_id: string | null;
  error: string | null;
  files: TakeFile[];
  created_at: string;
  finished_at: string | null;
  cancel_requested: boolean;
}

export interface Shot {
  id: string;
  title: string;
  notes: string;
  takes: Take[];
  selected_take: string | null;
}

export interface Project {
  format_version: number;
  title: string;
  shots: Shot[];
  created_at: string;
}

export interface ProjectOut {
  slug: string;
  project: Project;
}

export interface ProjectSummary {
  slug: string;
  title: string;
  shot_count: number;
  updated_at: string;
}

export interface MediaInfo {
  id: string;
  kind: "picture" | "video" | "audio";
  size: number;
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

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  // FastAPI validation errors: [{loc, msg}, …]
  if (Array.isArray(detail)) return detail.map((d) => String(d?.msg ?? d).replace(/^Value error, /, "")).join("; ");
  return JSON.stringify(detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    let code: string | undefined;
    try {
      const body = await res.json();
      code = body.code;
      detail = detailText(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail, code);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const p = (slug: string) => `/projects/${encodeURIComponent(slug)}`;
const post: RequestInit = { method: "POST" };

export const api = {
  settings: () => request<SettingsOut>("/settings"),
  saveSettings: (patch: { projects_dir?: string; comfyui_url?: string }) =>
    request<SettingsOut>("/settings", json("PUT", patch)),
  comfyui: () => request<ComfyStatus>("/comfyui"),
  options: () => request<Options>("/options"),

  projects: () => request<ProjectSummary[]>("/projects"),
  createProject: (title: string) => request<ProjectOut>("/projects", json("POST", { title })),
  project: (slug: string) => request<ProjectOut>(p(slug)),
  renameProject: (slug: string, title: string) => request<ProjectOut>(p(slug), json("PATCH", { title })),
  uploadMedia: (slug: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<MediaInfo>(`${p(slug)}/media`, { method: "POST", body: form });
  },

  addShot: (slug: string, after: string | null = null) => request<Shot>(`${p(slug)}/shots`, json("POST", { after })),
  editShot: (slug: string, shot: string, patch: { title?: string; notes?: string }) =>
    request<Shot>(`${p(slug)}/shots/${encodeURIComponent(shot)}`, json("PATCH", patch)),
  reorderShots: (slug: string, shots: string[]) => request<ProjectOut>(`${p(slug)}/shot-order`, json("PUT", { shots })),
  deleteShot: (slug: string, shot: string) =>
    request<void>(`${p(slug)}/shots/${encodeURIComponent(shot)}`, { method: "DELETE" }),

  generate: (slug: string, shot: string, body: GenerateRequest) =>
    request<Take>(`${p(slug)}/shots/${encodeURIComponent(shot)}/takes`, json("POST", body)),
  upscale: (slug: string, take: string) => request<Take>(`${p(slug)}/takes/${encodeURIComponent(take)}/upscale`, post),
  select: (slug: string, take: string) => request<Shot>(`${p(slug)}/takes/${encodeURIComponent(take)}/select`, post),
  cancel: (slug: string, take: string) => request<Take>(`${p(slug)}/takes/${encodeURIComponent(take)}/cancel`, post),
  deleteTake: (slug: string, take: string) =>
    request<void>(`${p(slug)}/takes/${encodeURIComponent(take)}`, { method: "DELETE" }),
};

export const mediaUrl = (slug: string, id: string) => `/api${p(slug)}/media/${encodeURIComponent(id)}`;
export const videoUrl = (slug: string, take: string) => `/api${p(slug)}/takes/${encodeURIComponent(take)}/video`;
