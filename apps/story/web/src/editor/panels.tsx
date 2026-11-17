import { useRef, useState } from "react";
import { api, fileUrl } from "../api";
import type { BaseProfile, StoryVariable } from "../generated/story";
import { Area, Num, Select, Text, ValueInput } from "./fields";
import { renameVariable, slugId } from "./storyOps";
import { useEditor } from "./useStoryEditor";

export function StoryPanel() {
  const { story, update } = useEditor();
  const s = story.settings;
  return (
    <div className="panel stack">
      <label>
        Title
        <Text value={story.title} onChange={(title) => update((d) => void (d.title = title))} />
      </label>
      <label>
        Description
        <Area rows={4} value={story.description} onChange={(v) => update((d) => void (d.description = v))} />
      </label>
      <label>
        Start scene
        <Select
          value={story.start_scene}
          options={story.scenes.map((x) => ({ value: x.id, label: x.title }))}
          empty="none"
          onChange={(v) => update((d) => void (d.start_scene = v))}
        />
      </label>
      <h3>Playback</h3>
      <label>
        Stage style
        <Select
          value={s.stage_style}
          options={[
            { value: "visual_novel", label: "Visual novel" },
            { value: "subtitles", label: "Subtitles" },
          ]}
          onChange={(v) => v && update((d) => void (d.settings.stage_style = v))}
        />
      </label>
      <label className="inline">
        Reading speed
        <Num value={s.reading_chars_per_s} min={1} onChange={(v) => update((d) => void (d.settings.reading_chars_per_s = v ?? 15))} />
        characters/s
      </label>
      <label className="inline">
        Shortest beat
        <Num value={s.min_beat_s} min={0.5} step={0.5} onChange={(v) => update((d) => void (d.settings.min_beat_s = v ?? 2.5))} />
        s
      </label>
      <h3>Audience weighting</h3>
      <label className="inline">
        Thumbs-up factor
        <Num value={s.thumbs_up_factor} min={0} step={0.25} onChange={(v) => update((d) => void (d.settings.thumbs_up_factor = v ?? 1))} />
      </label>
      <label className="inline">
        Match threshold
        <Num value={s.match_threshold} min={0} step={0.05} onChange={(v) => update((d) => void (d.settings.match_threshold = v ?? 0.35))} />
      </label>
      <p className="muted small">
        A message's weight is its match score × (1 + thumbs-ups × factor). Messages scoring under the threshold count as
        unmatched.
      </p>
    </div>
  );
}

const PROFILE_FIELDS: { key: keyof BaseProfile; label: string }[] = [
  { key: "summary", label: "Who they are" },
  { key: "personality", label: "Personality" },
  { key: "motivations", label: "Motivations" },
  { key: "speaking_style", label: "Speaking style" },
  { key: "knows", label: "Knows" },
  { key: "hides", label: "Hides" },
];

export function CharactersPanel() {
  const { story, update, assets, slug } = useEditor();
  const [name, setName] = useState("");
  const pictures = assets.filter((a) => a.kind === "picture");
  return (
    <div className="panel stack">
      <form
        className="inline"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          update((d) =>
            void d.characters.push({
              id: slugId(d, name, "character"),
              name: name.trim(),
              color: "#8a8f98",
              base_profile: { summary: "", personality: "", motivations: "", speaking_style: "", knows: "", hides: "" },
              portraits: [],
            }),
          );
          setName("");
        }}
      >
        <Text value={name} placeholder="New character name" onChange={setName} />
        <button className="small" disabled={!name.trim()}>
          Add
        </button>
      </form>
      {story.characters.map((c, i) => (
        <details key={c.id} className="card character-card">
          <summary>
            {c.portraits[0] && <img className="thumb" src={fileUrl(slug, c.portraits[0])} alt="" />}
            <strong style={{ color: c.color }}>{c.name}</strong>
          </summary>
          <div className="stack">
            <div className="inline">
              <Text value={c.name} onChange={(v) => update((d) => void (d.characters[i].name = v))} />
              <input type="color" value={c.color} onChange={(e) => update((d) => void (d.characters[i].color = e.target.value))} />
            </div>
            <span className="muted small">Base profile: the AI reads this whenever it writes {c.name || "them"}.</span>
            {PROFILE_FIELDS.map((f) => (
              <label key={f.key}>
                {f.label}
                <Area value={c.base_profile[f.key]} onChange={(v) => update((d) => void (d.characters[i].base_profile[f.key] = v))} />
              </label>
            ))}
            <label>
              Portrait
              <Select
                value={c.portraits[0] ?? null}
                options={pictures.map((a) => ({ value: a.path, label: a.path.replace(/^assets\//, "") }))}
                empty="none"
                onChange={(v) => update((d) => void (d.characters[i].portraits = v ? [v, ...c.portraits.slice(1).filter((p) => p !== v)] : c.portraits.slice(1)))}
              />
            </label>
            <button
              className="small danger"
              onClick={() => {
                if (!confirm(`Delete ${c.name}? Their lines become narrator lines.`)) return;
                update((d) => {
                  d.characters.splice(i, 1);
                  for (const s of d.scenes)
                    for (const step of s.steps)
                      for (const b of step.kind === "beat" ? [step] : step.lanes.flatMap((l) => l.beats))
                        b.lines.forEach((l) => l.speaker === c.id && (l.speaker = null));
                  d.memory_seed.forEach((m) => m.about === c.id && (m.about = null));
                });
              }}
            >
              Delete character
            </button>
          </div>
        </details>
      ))}
    </div>
  );
}

export function VariablesPanel() {
  const { story, update } = useEditor();
  const [draftNames, setDraftNames] = useState<Record<string, string>>({});
  const add = (type: StoryVariable["type"]) =>
    update((d) => {
      let name = `new_${type}`;
      for (let n = 2; d.variables.some((v) => v.name === name); n++) name = `new_${type}_${n}`;
      d.variables.push({ name, type, default: type === "number" ? 0 : type === "flag" ? false : "", description: "" });
    });
  return (
    <div className="panel stack">
      <p className="muted small">
        Story variables carry the consequences you design. Choices and beats change them; later beats, lanes and paths read
        them. Write <code>{"{name}"}</code> in a line to show a variable's value.
      </p>
      {story.variables.map((v, i) => {
        const draft = draftNames[v.name] ?? v.name;
        const valid = /^[a-z][a-z0-9_]{0,63}$/.test(draft) && (draft === v.name || !story.variables.some((x) => x.name === draft));
        return (
          <div key={i} className="card stack">
            <div className="inline">
              <input
                className={valid ? "" : "invalid"}
                value={draft}
                spellCheck={false}
                onChange={(e) => setDraftNames({ ...draftNames, [v.name]: e.target.value })}
                onBlur={() => {
                  if (valid && draft !== v.name) update((d) => renameVariable(d, v.name, draft));
                  setDraftNames(({ [v.name]: _, ...rest }) => rest);
                }}
              />
              <span className="badge">{v.type}</span>
              <button
                className="icon"
                title="Delete variable"
                onClick={() => confirm(`Delete ${v.name}? Anything using it will be flagged.`) && update((d) => void d.variables.splice(i, 1))}
              >
                ✕
              </button>
            </div>
            <label className="inline">
              Starts as
              <ValueInput variable={v} value={v.default} onChange={(val) => update((d) => void (d.variables[i].default = val))} />
            </label>
            <Text value={v.description} placeholder="What it tracks" onChange={(t) => update((d) => void (d.variables[i].description = t))} />
          </div>
        );
      })}
      <div className="inline">
        <span className="muted">Add:</span>
        <button className="small" onClick={() => add("number")}>
          number
        </button>
        <button className="small" onClick={() => add("flag")}>
          yes/no
        </button>
        <button className="small" onClick={() => add("text")}>
          text
        </button>
      </div>
    </div>
  );
}

export function MemoryPanel() {
  const { story, update } = useEditor();
  const characters = story.characters.map((c) => ({ value: c.id, label: c.name }));
  return (
    <div className="panel stack">
      <p className="muted small">
        Story memory starts with these notes. During a playthrough the AI adds its own (running jokes, backstory the audience
        established), and you can edit them from the Debug view.
      </p>
      {story.memory_seed.map((m, i) => (
        <div key={i} className="card stack">
          <Area value={m.text} onChange={(t) => update((d) => void (d.memory_seed[i].text = t))} />
          <div className="inline">
            <span className="muted">About</span>
            <Select value={m.about} options={characters} empty="the whole story" onChange={(v) => update((d) => void (d.memory_seed[i].about = v))} />
            <label className="inline">
              <input type="checkbox" checked={m.pinned} onChange={(e) => update((d) => void (d.memory_seed[i].pinned = e.target.checked))} />
              pinned
            </label>
            <button className="icon" onClick={() => update((d) => void d.memory_seed.splice(i, 1))}>
              ✕
            </button>
          </div>
        </div>
      ))}
      <button className="small" onClick={() => update((d) => void d.memory_seed.push({ text: "", about: null, pinned: false }))}>
        + note
      </button>
    </div>
  );
}

export function AssetsPanel() {
  const { assets, slug, refreshAssets } = useEditor();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function uploadAll(files: FileList | File[]) {
    setBusy(true);
    setError(null);
    try {
      for (const f of Array.from(files)) await api.uploadAsset(slug, f);
      await refreshAssets();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="panel stack"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        if (e.dataTransfer.files.length) void uploadAll(e.dataTransfer.files);
      }}
    >
      <button onClick={() => input.current?.click()} disabled={busy}>
        {busy ? "Uploading…" : "Add pictures, video or audio"}
      </button>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        accept="image/*,video/*,audio/*"
        onChange={(e) => {
          if (e.target.files) void uploadAll(e.target.files);
          e.target.value = "";
        }}
      />
      <span className="muted small">…or drop files here. They are copied into the project's assets folder.</span>
      {error && <p className="error">{error}</p>}
      <ul className="asset-grid">
        {assets.map((a) => (
          <li key={a.path} title={a.path}>
            {a.kind === "picture" ? (
              <img src={fileUrl(slug, a.path)} alt="" />
            ) : a.kind === "video" ? (
              <video src={fileUrl(slug, a.path)} muted preload="metadata" />
            ) : (
              <div className="audio-tile">♪</div>
            )}
            <span>{a.path.replace(/^assets\//, "")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
