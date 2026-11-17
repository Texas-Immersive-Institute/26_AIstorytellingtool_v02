import { useState } from "react";
import type { Audio, Frames, GenerateRequest, Options } from "../api";
import { MediaSlot } from "./MediaSlot";
import { AUDIO_LABEL, FRAMES_LABEL, estimateSpokenS, fitDuration, picturesNeeded } from "./defaults";

/** One take per generation, driven by the frame / audio / upscale toggles. */
export function GenerateForm({
  slug,
  options,
  draft,
  onChange,
  onGenerate,
  comfyReady,
}: {
  slug: string;
  options: Options;
  draft: GenerateRequest;
  onChange: (d: GenerateRequest) => void;
  onGenerate: (req: GenerateRequest) => Promise<void>;
  comfyReady: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<GenerateRequest>) => onChange({ ...draft, ...patch });
  const need = picturesNeeded(draft.frames);
  const pictures = Array.from({ length: need }, (_, i) => draft.pictures[i] || "");
  const voice = draft.voice ?? { clip: "", line: "", tone: "" };
  const setVoice = (patch: Partial<typeof voice>) => set({ voice: { ...voice, ...patch } });

  const missing = [
    !draft.prompt.trim() && "a prompt",
    pictures.some((p) => !p) && (need === 2 ? "both frames" : "a picture"),
    draft.audio === "clip" && !draft.audio_clip && "the audio clip",
    draft.audio === "voice" && !voice.clip && "the voice recording",
    draft.audio === "voice" && !voice.line.trim() && "the line to say",
  ].filter(Boolean) as string[];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (missing.length) return;
    const req: GenerateRequest = {
      ...draft,
      prompt: draft.prompt.trim(),
      pictures,
      audio_clip: draft.audio === "clip" ? draft.audio_clip : null,
      voice: draft.audio === "voice" ? { ...voice, line: voice.line.trim() } : null,
    };
    setBusy(true);
    setError(null);
    try {
      await onGenerate(req);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const spoken = voice.line.trim() ? estimateSpokenS(voice.line) : null;
  const frameLabels = draft.frames === "firstlast" ? ["First frame", "Last frame"] : [FRAMES_LABEL[draft.frames]];

  return (
    <form className="generate card" onSubmit={submit}>
      <h3>New take</h3>

      <label className="field">
        Prompt
        <textarea
          rows={5}
          value={draft.prompt}
          placeholder="What happens in this shot. Refer to the frame as <Picture 1>."
          onChange={(e) => set({ prompt: e.target.value })}
        />
      </label>

      <div className="field">
        Frames
        <Toggle<Frames>
          value={draft.frames}
          choices={options.frames}
          label={(f) => FRAMES_LABEL[f]}
          onChange={(frames) => set({ frames })}
        />
      </div>
      <div className="slots">
        {pictures.map((id, i) => (
          <MediaSlot
            key={i}
            slug={slug}
            kind="picture"
            label={frameLabels[i]}
            value={id || null}
            onChange={(value) => {
              const next = [...pictures];
              next[i] = value ?? "";
              set({ pictures: next });
            }}
          />
        ))}
      </div>

      <div className="field">
        Audio
        <Toggle<Audio>
          value={draft.audio}
          choices={options.audio}
          label={(a) => AUDIO_LABEL[a]}
          onChange={(audio) => set({ audio })}
        />
      </div>
      {draft.audio === "clip" && (
        <>
          <MediaSlot
            slug={slug}
            kind="audio"
            label="Audio clip (the exact soundtrack)"
            value={draft.audio_clip}
            onChange={(audio_clip) => set({ audio_clip })}
          />
          <p className="hint">The video's length follows the clip.</p>
        </>
      )}
      {draft.audio === "voice" && (
        <>
          <MediaSlot
            slug={slug}
            kind="audio"
            label="Voice recording (15–45 s of clean speech)"
            value={voice.clip || null}
            onChange={(clip) => setVoice({ clip: clip ?? "" })}
          />
          <label className="field">
            Line to say
            <textarea rows={2} value={voice.line} onChange={(e) => setVoice({ line: e.target.value })} />
          </label>
          <label className="field">
            Tone
            <input
              value={voice.tone}
              placeholder="optional, e.g. her tone is warm and amused"
              onChange={(e) => setVoice({ tone: e.target.value })}
            />
          </label>
          <p className="hint">
            {spoken
              ? `About ${spoken} s spoken → a ${fitDuration(spoken, options.durations)} s video. The spoken line sets the final length.`
              : "Takes speaks the line in this voice first, then animates the shot to it."}
          </p>
        </>
      )}

      <div className="field-row">
        {draft.audio === "native" && (
          <label className="field">
            Length
            <select value={draft.duration_s} onChange={(e) => set({ duration_s: Number(e.target.value) })}>
              {options.durations.map((d) => (
                <option key={d} value={d}>
                  {d} s
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="field">
          Size
          <select value={draft.aspect_ratio} onChange={(e) => set({ aspect_ratio: e.target.value })}>
            {options.aspect_ratios.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Seed
          <input
            className="seed"
            inputMode="numeric"
            placeholder="random"
            value={draft.seed ?? ""}
            onChange={(e) => {
              const digits = e.target.value.replace(/\D/g, "");
              set({ seed: digits ? Number(digits) : null });
            }}
          />
        </label>
      </div>

      <label className="check">
        <input type="checkbox" checked={draft.upscale} onChange={(e) => set({ upscale: e.target.checked })} />
        Upscale <span className="hint">slower; usually better to upscale a take you like</span>
      </label>

      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button className="primary" disabled={busy || missing.length > 0}>
          {busy ? "Sending…" : "Generate take"}
        </button>
        {missing.length > 0 && <span className="hint">Needs {missing.join(", ")}</span>}
        {missing.length === 0 && !comfyReady && <span className="hint warn">ComfyUI isn't ready, so this take would fail. Start the H3 ComfyUI first.</span>}
      </div>
    </form>
  );
}

function Toggle<T extends string>({
  value,
  choices,
  label,
  onChange,
}: {
  value: T;
  choices: T[];
  label: (v: T) => string;
  onChange: (v: T) => void;
}) {
  return (
    <div className="toggle" role="radiogroup">
      {choices.map((c) => (
        <button
          key={c}
          type="button"
          role="radio"
          aria-checked={c === value}
          className={c === value ? "on" : ""}
          onClick={() => onChange(c)}
        >
          {label(c)}
        </button>
      ))}
    </div>
  );
}
