import { useState } from "react";
import { api, type SettingsOut } from "../api";

export function Setup({ settings, onSaved }: { settings: SettingsOut; onSaved: (s: SettingsOut) => void }) {
  const [folder, setFolder] = useState(settings.projects_dir ?? settings.suggested_projects_dir);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.saveSettings(folder));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="centered">
      <form className="card setup" onSubmit={save}>
        <h1>Welcome to Story</h1>
        <p>
          Choose a folder for your story projects. Each story gets its own folder inside it, holding the outline,
          pictures, audio and saved playthroughs, so you can copy it to another computer.
        </p>
        <label>
          Projects folder
          <input value={folder} onChange={(e) => setFolder(e.target.value)} spellCheck={false} autoFocus />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" disabled={busy || !folder.trim()}>
          Use this folder
        </button>
      </form>
    </div>
  );
}
