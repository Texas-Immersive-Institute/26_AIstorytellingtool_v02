import { useEffect, useState } from "react";
import { api, type ProjectSummary, type SettingsOut } from "../api";
import { ComfyBadge, useComfy } from "../ComfyBadge";
import { go, href } from "../route";

export function Projects({ settings }: { settings: SettingsOut }) {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [comfy] = useComfy();

  useEffect(() => {
    api
      .projects()
      .then((list) => setProjects([...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at))))
      .catch((e: Error) => setError(e.message));
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      const made = await api.createProject(title.trim());
      go({ name: "project", slug: made.slug, shot: null });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="page">
      <header className="topbar">
        <h1>Takes</h1>
        <ComfyBadge status={comfy} />
        <a className="button" href="#/settings">
          Settings
        </a>
      </header>
      <p className="muted folder" title={settings.projects_dir ?? ""}>
        {settings.projects_dir}
      </p>

      <h2>New project</h2>
      <form className="row" onSubmit={create}>
        <input placeholder="Project title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <button className="primary" disabled={!title.trim()}>
          Create
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      <h2>Projects</h2>
      {projects === null ? (
        <p className="muted">Loading…</p>
      ) : projects.length === 0 ? (
        <p className="muted">No projects yet. Create one above.</p>
      ) : (
        <ul className="cards">
          {projects.map((p) => (
            <li key={p.slug}>
              <a className="card project" href={href({ name: "project", slug: p.slug, shot: null })}>
                <strong>{p.title}</strong>
                <span className="muted">
                  {p.shot_count} {p.shot_count === 1 ? "shot" : "shots"} · {new Date(p.updated_at).toLocaleString()}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
