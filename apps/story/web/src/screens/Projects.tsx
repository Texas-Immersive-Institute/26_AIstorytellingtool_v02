import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ExampleOut, type ProjectSummary, type SettingsOut } from "../api";
import { go } from "../route";

export function Projects({ settings, onChangeFolder }: { settings: SettingsOut; onChangeFolder: () => void }) {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [examples, setExamples] = useState<ExampleOut[]>([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const importInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.projects().then(setProjects).catch((e: Error) => setError(e.message));
    api.examples().then(setExamples).catch(() => setExamples([]));
  }, []);
  useEffect(load, [load]);

  async function run(action: () => Promise<{ slug: string }>) {
    setError(null);
    try {
      const { slug } = await action();
      go({ name: "project", slug });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="page">
      <header className="topbar">
        <h1>Story</h1>
        <span className="muted folder" title={settings.projects_dir ?? ""}>
          {settings.projects_dir}
        </span>
        <button className="link" onClick={onChangeFolder}>
          Change folder
        </button>
        <a className="button" href="#/settings">
          ⚙ Settings
        </a>
        <a className="button" href="#/stage" target="_blank" rel="noreferrer">
          Open Stage ↗
        </a>
      </header>
      {error && <p className="error">{error}</p>}

      <section>
        <h2>Your stories</h2>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) run(() => api.createProject(title.trim()));
          }}
        >
          <input placeholder="New story title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <button className="primary" disabled={!title.trim()}>
            New story
          </button>
          <button type="button" onClick={() => importInput.current?.click()}>
            Import .zip
          </button>
          <input
            ref={importInput}
            type="file"
            accept=".zip"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) run(() => api.importProject(file));
            }}
          />
        </form>
        {projects === null ? (
          <p className="muted">Loading…</p>
        ) : projects.length === 0 ? (
          <p className="muted">No stories yet. Start a new one, or copy an example below.</p>
        ) : (
          <ul className="cards">
            {projects.map((p) => (
              <li key={p.slug}>
                <a className="card project" href={`#/project/${encodeURIComponent(p.slug)}`}>
                  <strong>{p.title}</strong>
                  <span className="muted">
                    {p.scene_count} scene{p.scene_count === 1 ? "" : "s"} · {new Date(p.updated_at).toLocaleString()}
                  </span>
                  {p.description && <span className="desc">{p.description}</span>}
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      {examples.length > 0 && (
        <section>
          <h2>Examples</h2>
          <ul className="cards">
            {examples.map((ex) => (
              <li key={ex.name} className="card">
                <strong>{ex.title}</strong>
                <span className="desc">{ex.description}</span>
                <button onClick={() => run(() => api.copyExample(ex.name))}>Copy to my stories</button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
