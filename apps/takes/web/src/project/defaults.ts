import { UNFINISHED, type GenerateRequest, type RenderProgress, type Shot, type Take, type TakeStatus } from "../api";

export const DEFAULT_ASPECT = "9:16 (Portrait Widescreen)";

export function blankRequest(): GenerateRequest {
  return {
    prompt: "",
    frames: "first",
    audio: "native",
    upscale: false,
    pictures: [],
    audio_clip: null,
    voice: null,
    duration_s: 6.58,
    aspect_ratio: DEFAULT_ASPECT,
    seed: null,
    continues: null,
  };
}

/** A new take starts from the shot's newest take (not an upscale: that one is a re-render). */
export function draftFor(shot: Shot): GenerateRequest {
  const last = [...shot.takes].reverse().find((t) => !t.source_take);
  const draft = last ? reuse(last) : blankRequest();
  // A continuation shot always carries on from its take, from that take's video (no pictures).
  return shot.continues_take ? { ...draft, continues: shot.continues_take, frames: "none", pictures: [] } : draft;
}

/** The shot and take a continuation shot carries on from. */
export function continuedFrom(shots: Shot[], shot: Shot): { shot: Shot; number: number; take: Take } | null {
  if (!shot.continues_take) return null;
  for (const [i, s] of shots.entries()) {
    const take = s.takes.find((t) => t.id === shot.continues_take);
    if (take) return { shot: s, number: i + 1, take };
  }
  return null;
}

/** H3's extend stages overlap the continued video's last 22 frames (pack: overlap_frames). */
export const EXTEND_OVERLAP_S = 22 / 24;

/** A take's settings, ready to generate another take like it (on a new seed). */
export function reuse(take: Take): GenerateRequest {
  return { ...blankRequest(), ...take.request, seed: null };
}

export const picturesNeeded = (frames: GenerateRequest["frames"]) =>
  frames === "none" ? 0 : frames === "firstlast" ? 2 : 1;

/** The shortest H3 length that holds `seconds` of sound (mirrors stages.fit_duration). */
export function fitDuration(seconds: number, durations: number[]): number {
  return durations.find((d) => d >= seconds - 0.005) ?? durations[durations.length - 1];
}

/** About 2.7 spoken words a second plus a breath (mirrors stages.estimate_spoken_s). */
export function estimateSpokenS(line: string): number {
  const words = line.split(/\s+/).filter(Boolean).length;
  return Math.min(15, Math.max(1, Math.round((words / 2.7 + 0.6) * 100) / 100));
}

export const isUnfinished = (status: TakeStatus) => UNFINISHED.includes(status);

export const STATUS_LABEL: Record<TakeStatus, string> = {
  queued: "Waiting",
  preparing: "Preparing",
  voicing: "Speaking the line",
  rendering: "Rendering",
  downloading: "Copying files",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const FRAMES_LABEL = {
  none: "No picture",
  first: "First frame",
  last: "Last frame",
  firstlast: "First + last",
} as const;
export const AUDIO_LABEL = { native: "Native", clip: "Your clip", voice: "Voice reference" } as const;

/** The name a media id was uploaded with (ids are "<8 hex>-<name>"). */
export const mediaName = (id: string) => id.replace(/^[0-9a-f]{8}-/, "");

export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** One shot in the sequence: its selected take (if finished) and where that take starts playing. */
export interface SequenceEntry {
  shot: Shot;
  number: number; // 1-based position in the shot list
  take: Take | null; // null: the shot has no finished selected take and is skipped
  from_s: number;
  length_s: number | null; // what plays: the take's length minus its in-point
}

export function sequenceOf(shots: Shot[]): SequenceEntry[] {
  return shots.map((shot, i) => {
    const take = shot.takes.find((t) => t.id === shot.selected_take && t.status === "done") ?? null;
    const from_s = take?.play_from_s ?? 0;
    const length_s = take?.duration_s != null ? Math.max(0, take.duration_s - from_s) : null;
    return { shot, number: i + 1, take, from_s, length_s };
  });
}

/** What ComfyUI is doing, in words, from the node type that's running. */
export function progressLabel(p: RenderProgress): string {
  const node = p.node ?? "";
  const what = /sampler/i.test(node)
    ? "Sampling"
    : /rife|interpol/i.test(node)
      ? "Smoothing to 48 fps"
      : /upscal/i.test(node)
        ? "Upscaling"
        : /decode/i.test(node)
          ? "Decoding"
          : /videocombine|save/i.test(node)
            ? "Saving"
            : /loader|load/i.test(node)
              ? "Loading models"
              : node || "Working";
  return p.step != null && p.steps && p.steps > 1 ? `${what} · step ${p.step} of ${p.steps}` : what;
}

export function takeLabel(shot: Shot, take: Take): string {
  return `Take ${shot.takes.indexOf(take) + 1}`;
}
