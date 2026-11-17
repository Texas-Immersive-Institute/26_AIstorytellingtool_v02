import { useState } from "react";
import { api, type SettingsOut } from "../api";
import { ComfyBadge, useComfy } from "../ComfyBadge";

export function Settings({ settings, onSaved }: { settings: SettingsOut; onSaved: (s: SettingsOut) => void }) {
  const [folder, setFolder] = useState(settings.projects_dir ?? "");
  const [url, setUrl] = useState(settings.comfyui_url ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [comfy, recheck] = useComfy();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      onSaved(await api.saveSettings({ projects_dir: folder, comfyui_url: url }));
      setSaved(true);
      recheck();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="page narrow">
      <header className="topbar">
        <h1>Settings</h1>
        <a className="button" href="#/">
          Back to projects
        </a>
      </header>
      <form className="card setup" onSubmit={save}>
        <label>
          Projects folder
          <input value={folder} onChange={(e) => setFolder(e.target.value)} />
        </label>
        <label>
          ComfyUI address
          <input
            value={url}
            placeholder={`${settings.default_comfyui_url} (this computer)`}
            onChange={(e) => setUrl(e.target.value)}
          />
          <span className="hint">Leave empty for ComfyUI on this computer. ComfyUI must already be running.</span>
        </label>
        {error && <p className="error">{error}</p>}
        <div className="buttons">
          <button className="primary">Save</button>
          {saved && <span className="muted">Saved.</span>}
        </div>
      </form>

      <h2>ComfyUI</h2>
      <div className="card">
        <div className="buttons">
          <ComfyBadge status={comfy} />
          <button type="button" onClick={recheck}>
            Check again
          </button>
        </div>
        {comfy && (
          <dl className="facts">
            <dt>Address</dt>
            <dd>{comfy.url}</dd>
            {comfy.version && (
              <>
                <dt>Version</dt>
                <dd>{comfy.version}</dd>
              </>
            )}
            {comfy.gpus.length > 0 && (
              <>
                <dt>GPU</dt>
                <dd>{comfy.gpus.join(", ")}</dd>
              </>
            )}
            {comfy.message && (
              <>
                <dt>Status</dt>
                <dd>{comfy.message}</dd>
              </>
            )}
          </dl>
        )}
      </div>
    </div>
  );
}
