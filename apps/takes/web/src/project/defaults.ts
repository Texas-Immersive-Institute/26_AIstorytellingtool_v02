import { UNFINISHED, type GenerateRequest, type Shot, type Take, type TakeStatus } from "../api";

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
  };
}

/** A new take starts from the shot's newest take (not an upscale: that one is a re-render). */
export function draftFor(shot: Shot): GenerateRequest {
  const last = [...shot.takes].reverse().find((t) => !t.source_take);
  return last ? reuse(last) : blankRequest();
}

/** A take's settings, ready to generate another take like it (on a new seed). */
export function reuse(take: Take): GenerateRequest {
  return { ...blankRequest(), ...take.request, seed: null };
}

export const picturesNeeded = (frames: GenerateRequest["frames"]) => (frames === "firstlast" ? 2 : 1);

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

export const FRAMES_LABEL = { first: "First frame", last: "Last frame", firstlast: "First + last" } as const;
export const AUDIO_LABEL = { native: "Native", clip: "Your clip", voice: "Voice reference" } as const;

/** The name a media id was uploaded with (ids are "<8 hex>-<name>"). */
export const mediaName = (id: string) => id.replace(/^[0-9a-f]{8}-/, "");

export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function takeLabel(shot: Shot, take: Take): string {
  return `Take ${shot.takes.indexOf(take) + 1}`;
}
