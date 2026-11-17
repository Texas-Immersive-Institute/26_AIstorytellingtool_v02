import { useRef, useState } from "react";
import type { ChoicePoint, Condition, Effect, MediaSlot, StoryVariable, Value } from "../generated/story";
import { api, fileUrl } from "../api";
import { useEditor } from "./useStoryEditor";
import { defaultOp, defaultValue, idMaker, newCondition, newEffect } from "./storyOps";

export function Text({
  value,
  onChange,
  placeholder,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <input className={className} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
  );
}

export function Area({
  value,
  onChange,
  placeholder,
  rows = 2,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return <textarea value={value} rows={rows} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />;
}

export function Num({
  value,
  onChange,
  min,
  step = 1,
  placeholder,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  min?: number;
  step?: number;
  placeholder?: string;
}) {
  return (
    <input
      type="number"
      className="num"
      value={value ?? ""}
      min={min}
      step={step}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
    />
  );
}

export function Select<T extends string>({
  value,
  options,
  onChange,
  empty,
}: {
  value: T | null;
  options: { value: T; label: string }[];
  onChange: (v: T | null) => void;
  empty?: string;
}) {
  const known = value === null || options.some((o) => o.value === value);
  return (
    <select value={value ?? ""} onChange={(e) => onChange((e.target.value || null) as T | null)}>
      {empty !== undefined && <option value="">{empty}</option>}
      {!known && <option value={value!}>{value} (missing)</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** A value input shaped by the variable's type. */
export function ValueInput({
  variable,
  value,
  onChange,
}: {
  variable: StoryVariable | undefined;
  value: Value;
  onChange: (v: Value) => void;
}) {
  if (variable?.type === "flag")
    return (
      <select value={String(value === true)} onChange={(e) => onChange(e.target.value === "true")}>
        <option value="true">yes</option>
        <option value="false">no</option>
      </select>
    );
  if (variable?.type === "number")
    return <Num value={typeof value === "number" ? value : null} step={0.5} onChange={(v) => onChange(v)} />;
  return <Text value={typeof value === "string" ? value : ""} placeholder="text" onChange={(v) => onChange(v)} />;
}

const CONDITION_OPS: { value: Condition["op"]; label: string; types: StoryVariable["type"][] }[] = [
  { value: "eq", label: "=", types: ["number", "flag", "text"] },
  { value: "ne", label: "≠", types: ["number", "flag", "text"] },
  { value: "lt", label: "<", types: ["number"] },
  { value: "le", label: "≤", types: ["number"] },
  { value: "gt", label: ">", types: ["number"] },
  { value: "ge", label: "≥", types: ["number"] },
  { value: "contains", label: "contains", types: ["text"] },
  { value: "is_set", label: "is set", types: ["number", "flag", "text"] },
  { value: "not_set", label: "is not set", types: ["number", "flag", "text"] },
];

export function ConditionEditor({ value, onChange }: { value: Condition; onChange: (c: Condition) => void }) {
  const { story } = useEditor();
  const variable = story.variables.find((v) => v.name === value.variable);
  const ops = CONDITION_OPS.filter((o) => !variable || o.types.includes(variable.type));
  return (
    <span className="inline">
      <Select
        value={value.variable || null}
        options={story.variables.map((v) => ({ value: v.name, label: v.name }))}
        empty="variable…"
        onChange={(name) => {
          const v = story.variables.find((x) => x.name === name);
          onChange({ variable: name ?? "", op: v ? defaultOp(v) : "eq", value: v ? defaultValue(v) : null });
        }}
      />
      <Select value={value.op} options={ops} onChange={(op) => op && onChange({ ...value, op })} />
      {value.op !== "is_set" && value.op !== "not_set" && (
        <ValueInput variable={variable} value={value.value} onChange={(v) => onChange({ ...value, value: v })} />
      )}
    </span>
  );
}

const EFFECT_OPS: { value: Effect["op"]; label: string; types: StoryVariable["type"][] }[] = [
  { value: "set", label: "set to", types: ["number", "flag", "text"] },
  { value: "add", label: "add", types: ["number"] },
  { value: "toggle", label: "toggle", types: ["flag"] },
  { value: "clear", label: "clear", types: ["number", "flag", "text"] },
];

export function EffectsEditor({ value, onChange }: { value: Effect[]; onChange: (e: Effect[]) => void }) {
  const { story } = useEditor();
  return (
    <div className="stack">
      {value.map((eff, i) => {
        const variable = story.variables.find((v) => v.name === eff.variable);
        const ops = EFFECT_OPS.filter((o) => !variable || o.types.includes(variable.type));
        const set = (patch: Partial<Effect>) => onChange(value.map((e, j) => (j === i ? { ...e, ...patch } : e)));
        return (
          <span className="inline" key={i}>
            <Select
              value={eff.variable || null}
              options={story.variables.map((v) => ({ value: v.name, label: v.name }))}
              empty="variable…"
              onChange={(name) => {
                const v = story.variables.find((x) => x.name === name);
                set({ variable: name ?? "", op: v?.type === "number" ? "add" : "set", value: v ? defaultValue(v) : null });
              }}
            />
            <Select value={eff.op} options={ops} onChange={(op) => op && set({ op })} />
            {(eff.op === "set" || eff.op === "add") && (
              <ValueInput variable={variable} value={eff.value} onChange={(v) => set({ value: v })} />
            )}
            <button className="icon" title="Remove effect" onClick={() => onChange(value.filter((_, j) => j !== i))}>
              ✕
            </button>
          </span>
        );
      })}
      <button className="small" disabled={!story.variables.length} onClick={() => onChange([...value, newEffect(story)])}>
        + change a variable
      </button>
    </div>
  );
}

export function ConditionToggle({
  value,
  onChange,
  label,
}: {
  value: Condition | null;
  onChange: (c: Condition | null) => void;
  label: string;
}) {
  const { story } = useEditor();
  if (!value)
    return (
      <button className="small" disabled={!story.variables.length} onClick={() => onChange(newCondition(story))}>
        + {label}
      </button>
    );
  return (
    <span className="inline">
      <span className="muted">{label}</span>
      <ConditionEditor value={value} onChange={onChange} />
      <button className="icon" title="Remove condition" onClick={() => onChange(null)}>
        ✕
      </button>
    </span>
  );
}

/** A choice point and its options. `targets` are the scenes or lanes an option can lead to. */
export function ChoiceEditor({
  value,
  onChange,
  targets,
  targetLabel,
}: {
  value: ChoicePoint;
  onChange: (c: ChoicePoint) => void;
  targets: { value: string; label: string }[];
  targetLabel: string;
}) {
  const { story } = useEditor();
  const setOption = (i: number, patch: Partial<ChoicePoint["options"][number]>) =>
    onChange({ ...value, options: value.options.map((o, j) => (j === i ? { ...o, ...patch } : o)) });
  return (
    <div className="choice stack">
      <label>
        Ask the audience
        <Text value={value.prompt} placeholder="What should happen?" onChange={(prompt) => onChange({ ...value, prompt })} />
      </label>
      <label className="inline">
        Countdown
        <Num value={value.countdown_s} min={1} onChange={(v) => onChange({ ...value, countdown_s: v ?? 30 })} /> s
      </label>
      {value.options.map((o, i) => (
        <div className="option" key={o.id}>
          <div className="inline">
            <Text value={o.label} placeholder="Option label" onChange={(label) => setOption(i, { label })} />
            <span className="muted">→</span>
            <Select
              value={o.goes_to}
              options={targets}
              empty={`${targetLabel}…`}
              onChange={(goes_to) => setOption(i, { goes_to })}
            />
            <button
              className="icon"
              title="Remove option"
              onClick={() => onChange({ ...value, options: value.options.filter((_, j) => j !== i) })}
            >
              ✕
            </button>
          </div>
          <Text
            value={o.meaning}
            placeholder="What it means, for matching chat (optional)"
            className="meaning"
            onChange={(meaning) => setOption(i, { meaning })}
          />
          <EffectsEditor value={o.effects} onChange={(effects) => setOption(i, { effects })} />
        </div>
      ))}
      <button
        className="small"
        onClick={() =>
          onChange({
            ...value,
            options: [
              ...value.options,
              { id: idMaker(story)("opt"), label: "", meaning: "", goes_to: null, effects: [] },
            ],
          })
        }
      >
        + option
      </button>
    </div>
  );
}

export function MediaSlotEditor({
  label,
  value,
  onChange,
  kinds,
}: {
  label: string;
  value: MediaSlot;
  onChange: (s: MediaSlot) => void;
  kinds: ("picture" | "video" | "audio")[];
}) {
  const { assets, slug, refreshAssets } = useEditor();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const choices = assets.filter((a) => kinds.includes(a.kind));
  const chosen = assets.find((a) => a.path === value.asset);
  const noun = kinds.includes("audio") ? "audio files" : "pictures or videos";
  const accept = kinds.map((k) => (k === "picture" ? "image/*" : `${k}/*`)).join(",");

  // Upload into the project's assets folder and use the file in this slot straight away.
  async function upload(file: File | undefined) {
    if (!file) return;
    const kind = file.type.startsWith("image/") ? "picture" : file.type.split("/")[0];
    if (!kinds.includes(kind as (typeof kinds)[number])) {
      setError(`This slot takes ${noun}.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const info = await api.uploadAsset(slug, file);
      await refreshAssets();
      onChange({ mode: "set", asset: info.path });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`slot${over ? " drop" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        void upload(e.dataTransfer.files[0]);
      }}
    >
      <div className="inline">
        <span className="slot-label">{label}</span>
        <div className="segmented">
          {(["hold", "set", "clear"] as const).map((m) => (
            <button
              key={m}
              className={value.mode === m ? "on" : ""}
              title={
                m === "hold"
                  ? `Keep the ${label.toLowerCase()} from the beat before`
                  : m === "set"
                    ? `Use a file from this project`
                    : `No ${label.toLowerCase()}`
              }
              onClick={() => onChange({ ...value, mode: m })}
            >
              {m === "hold" ? "Hold" : m === "set" ? "File" : "None"}
            </button>
          ))}
        </div>
        <button className="small" disabled={busy} title={`Upload ${noun} (or drop a file here)`} onClick={() => input.current?.click()}>
          {busy ? "Uploading…" : "Upload…"}
        </button>
        <input
          ref={input}
          type="file"
          hidden
          accept={accept}
          onChange={(e) => {
            void upload(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {value.mode === "set" &&
        (choices.length === 0 ? (
          <span className="muted small">No {noun} in this project yet. Upload one, or drop a file here.</span>
        ) : (
          <Select
            value={value.asset}
            options={choices.map((a) => ({ value: a.path, label: a.path.replace(/^assets\//, "") }))}
            empty="choose a file…"
            onChange={(asset) => onChange({ ...value, asset })}
          />
        ))}
      {value.mode === "set" && chosen?.kind === "picture" && <img className="slot-preview" src={fileUrl(slug, chosen.path)} alt="" />}
      {value.mode === "set" && chosen?.kind === "video" && (
        <video className="slot-preview" src={fileUrl(slug, chosen.path)} muted preload="metadata" />
      )}
      {value.mode === "set" && chosen?.kind === "audio" && <audio controls preload="none" src={fileUrl(slug, chosen.path)} />}
      {error && <span className="error small">{error}</span>}
    </div>
  );
}
