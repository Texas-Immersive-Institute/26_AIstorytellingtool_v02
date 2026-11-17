import { useState } from "react";
import type { Audio, Frames, GenerateRequest, Options } from "../api";
import { MediaSlot } from "./MediaSlot";
import { AUDIO_LABEL, EXTEND_OVERLAP_S, FRAMES_LABEL, estimateSpokenS, fitDuration, picturesNeeded } from "./defaults";

/** One take per generation, driven by the frame / audio / upscale toggles. */
export function GenerateForm({
  slug,
  options,
  draft,
  continued,
  onChange,
  onGenerate,
  comfyReady,
}: {
  slug: string;
  options: Options;
  draft: GenerateRequest;
  /** For a continuation shot: the take it carries on from. */
  continued: { label: string; shotId: string } | null;
  onChange: (d: GenerateRequest) => void;
  onGenerate: (req: GenerateRequest) => Promise<void>;
  comfyReady: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<GenerateRequest>) => onChange({ ...draft, ...patch });
  const extending = !!continued;
  const need = extending ? 0 : picturesNeeded(draft.frames);
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
      upscale: draft.upscale && (!extending || draft.audio === "native"),
      frames: extending ? "none" : draft.frames,
      continues: extending ? draft.continues : null,
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
      <h3>{extending ? "New take: extension" : "New take"}</h3>
      {continued && (
        <p className="hint continues">
          Carries on from the end of{" "}
          <a href={`#/project/${encodeURIComponent(slug)}/${encodeURIComponent(continued.shotId)}`}>{continued.label}</a>.
          That take is <code>&lt;Video 1&gt;</code>. Describe only what happens next, starting with “Continue
          seamlessly from the previous scene.”
        </p>
      )}

      <label className="field">
        Prompt
        <textarea
          rows={5}
          value={draft.prompt}
          placeholder={
            extending
              ? "integrated_multimodal_description: [Shot 1] Continue seamlessly from the previous scene. …"
              : need
                ? "What happens in this shot. Refer to the frame as <Picture 1>."
                : "What happens in this shot."
          }
          onChange={(e) => set({ prompt: e.target.value })}
        />
      </label>

      {!extending && (
        <div className="field">
          Frames
          <Toggle<Frames>
            value={draft.frames}
            choices={options.frames}
            label={(f) => FRAMES_LABEL[f]}
            onChange={(frames) => set({ frames })}
          />
        </div>
      )}
      {!extending && need === 0 && (
        <p className="hint">
          The prompt alone sets the scene. Start it with <code>integrated_multimodal_description:</code> and
          no picture line.
        </p>
      )}
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
          <label
            className="field"
            title={extending ? "The new part, including its overlap with the continued take" : undefined}
          >
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

      {extending && draft.audio === "native" && (
        <p className="hint">
          Adds about {Math.max(0, draft.duration_s - EXTEND_OVERLAP_S).toFixed(1)} s of new footage (the length minus
          the overlap with the continued take).
        </p>
      )}

      <label className="check">
        <input
          type="checkbox"
          checked={draft.upscale && (!extending || draft.audio === "native")}
          disabled={extending && draft.audio !== "native"}
          onChange={(e) => set({ upscale: e.target.checked })}
        />
        Upscale{" "}
        <span className="hint">
          {extending && draft.audio !== "native"
            ? "not with your clip or a voice reference when extending"
            : extending
              ? "the new part only; slower"
              : "slower; usually better to upscale a take you like"}
        </span>
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
