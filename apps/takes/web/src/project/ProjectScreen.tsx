import { useCallback, useEffect, useRef, useState } from "react";
import { api, type GenerateRequest, type Options, type Project, type Take } from "../api";
import { ComfyBadge, useComfy } from "../ComfyBadge";
import { go } from "../route";
import { draftFor, isUnfinished, reuse, takeLabel } from "./defaults";
import { GenerateForm } from "./GenerateForm";
import { ShotList } from "./ShotList";
import { TakeList, type TakeActions } from "./TakeList";

export function ProjectScreen({ slug, shotId }: { slug: string; shotId: string | null }) {
  const [project, setProject] = useState<Project | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comfy] = useComfy();
  // The generate form's contents per shot, kept while you move between shots.
  const drafts = useRef(new Map<string, GenerateRequest>());
  const [, redraw] = useState(0);

  const load = useCallback(
    () =>
      api
        .project(slug)
        .then((out) => setProject(out.project))
        .catch((e: Error) => setError(e.message)),
    [slug],
  );

  useEffect(() => {
    load();
    api.options().then(setOptions, (e: Error) => setError(e.message));
  }, [load]);

  // While anything renders, refresh every 2 s to follow its progress.
  const rendering = project?.shots.some((s) => s.takes.some((t) => isUnfinished(t.status))) ?? false;
  useEffect(() => {
    if (!rendering) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [rendering, load]);

  const shot = project?.shots.find((s) => s.id === shotId) ?? project?.shots[0] ?? null;
  const open = (id: string) => go({ name: "project", slug, shot: id }, true);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError((err as Error).message);
    }
    await load();
  }

  if (!project || !options) {
    return <div className="centered">{error ? <span className="error">{error}</span> : "Loading…"}</div>;
  }

  const draft = shot ? (drafts.current.get(shot.id) ?? draftFor(shot)) : null;
  const setDraft = (d: GenerateRequest) => {
    if (!shot) return;
    drafts.current.set(shot.id, d);
    redraw((n) => n + 1);
  };

  const actions: TakeActions = {
    select: (t) => run(() => api.select(slug, t.id)),
    upscale: (t) => run(() => api.upscale(slug, t.id)),
    cancel: (t) => run(() => api.cancel(slug, t.id)),
    remove: (t: Take) => {
      if (shot && confirm(`Delete ${takeLabel(shot, t)} and its files?`)) run(() => api.deleteTake(slug, t.id));
    },
    reuse: (t) => setDraft(reuse(t)),
  };

  async function addShot(after: string | null = null) {
    setError(null);
    try {
      const made = await api.addShot(slug, after);
      await load();
      open(made.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function reorder(ids: string[]) {
    const byId = new Map(project!.shots.map((s) => [s.id, s]));
    setProject({ ...project!, shots: ids.map((id) => byId.get(id)!) }); // show it right away
    await run(() => api.reorderShots(slug, ids));
  }

  async function deleteShot() {
    if (!shot || !confirm(`Delete "${shot.title}" and all ${shot.takes.length} of its takes?`)) return;
    const index = project!.shots.indexOf(shot);
    const next = project!.shots[index + 1] ?? project!.shots[index - 1];
    await run(() => api.deleteShot(slug, shot.id));
    go({ name: "project", slug, shot: next?.id ?? null }, true);
  }

  return (
    <div className="project">
      <header className="topbar bar">
        <a href="#/" className="button">
          ← Projects
        </a>
        <EditableTitle value={project.title} onSave={(title) => run(() => api.renameProject(slug, title))} />
        {error && (
          <span className="error bar-error" onClick={() => setError(null)} title="Click to dismiss">
            {error}
          </span>
        )}
        <ComfyBadge status={comfy} />
        <a className="button" href="#/settings">
          Settings
        </a>
      </header>

      <div className="workspace">
        <ShotList shots={project.shots} current={shot?.id ?? null} onOpen={open} onReorder={reorder} onAdd={() => addShot()} />

        {shot && draft ? (
          <main className="shot">
            <div className="shot-head">
              <ShotFields
                key={shot.id}
                title={shot.title}
                notes={shot.notes}
                onSave={(patch) => run(() => api.editShot(slug, shot.id, patch))}
              />
              <div className="buttons">
                <button onClick={() => addShot(shot.id)}>+ Shot after this</button>
                <button className="danger" onClick={deleteShot}>
                  Delete shot
                </button>
              </div>
            </div>
            <div className="shot-body">
              <TakeList slug={slug} shot={shot} actions={actions} />
              <GenerateForm
                key={shot.id}
                slug={slug}
                options={options}
                draft={draft}
                onChange={setDraft}
                comfyReady={comfy?.ready ?? false}
                onGenerate={async (req) => {
                  await api.generate(slug, shot.id, req);
                  setDraft({ ...req, seed: null });
                  await load();
                }}
              />
            </div>
          </main>
        ) : (
          <main className="shot empty">
            <p className="muted">This project has no shots yet.</p>
            <button className="primary" onClick={() => addShot()}>
              Add the first shot
            </button>
          </main>
        )}
      </div>
    </div>
  );
}

function EditableTitle({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const commit = () => text.trim() && text.trim() !== value && onSave(text.trim());
  return (
    <input
      className="title-input"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      aria-label="Project title"
    />
  );
}

function ShotFields({
  title,
  notes,
  onSave,
}: {
  title: string;
  notes: string;
  onSave: (patch: { title?: string; notes?: string }) => void;
}) {
  const [t, setT] = useState(title);
  const [n, setN] = useState(notes);
  useEffect(() => setT(title), [title]);
  useEffect(() => setN(notes), [notes]);
  return (
    <div className="shot-fields">
      <input
        className="shot-title-input"
        value={t}
        aria-label="Shot title"
        onChange={(e) => setT(e.target.value)}
        onBlur={() => t.trim() && t !== title && onSave({ title: t })}
        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      />
      <textarea
        rows={2}
        value={n}
        placeholder="Notes for this shot"
        onChange={(e) => setN(e.target.value)}
        onBlur={() => n !== notes && onSave({ notes: n })}
      />
    </div>
  );
}
