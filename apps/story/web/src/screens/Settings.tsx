import { useEffect, useState } from "react";
import { api, type AiSettings, type AiStatus, type BackendChoice, type LanInfo, type MatchingStatus, type SettingsOut } from "../api";

const BACKENDS: { value: BackendChoice; label: string; note: string }[] = [
  { value: "auto", label: "Automatic", note: "Uses the first one that's ready: Ollama, then the Claude CLI, then the Codex CLI." },
  { value: "ollama", label: "Ollama (local)", note: "A model on this computer. Free, but shares the GPU with ComfyUI." },
  { value: "claude_cli", label: "Claude CLI", note: "Uses your Claude subscription. A few seconds per line." },
  { value: "codex_cli", label: "Codex CLI", note: "Uses your ChatGPT subscription. Around 10 seconds per line." },
  { value: "none", label: "Off", note: "AI lines always play their default line." },
];

export function Settings({ settings, onChangeFolder }: { settings: SettingsOut; onChangeFolder: () => void }) {
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [saved, setSaved] = useState<AiSettings | null>(null);
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [test, setTest] = useState<string | null>(null);
  const [matching, setMatching] = useState<MatchingStatus | null>(null);
  const [lan, setLan] = useState<LanInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.aiSettings().then((s) => {
      setAi(s);
      setSaved(s);
    });
    api.matchingStatus().then(setMatching).catch(() => setMatching(null));
    api.lan().then(setLan).catch(() => setLan(null));
    void check();
  }, []);

  // While the embedding model downloads, poll its status.
  useEffect(() => {
    if (!matching?.downloading) return;
    const t = window.setInterval(() => api.matchingStatus().then(setMatching), 1500);
    return () => window.clearInterval(t);
  }, [matching?.downloading]);

  async function check() {
    setChecking(true);
    try {
      setStatus(await api.aiStatus());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  }

  async function save() {
    if (!ai) return;
    setError(null);
    try {
      const s = await api.saveAiSettings(ai);
      setAi(s);
      setSaved(s);
      setTest(null);
      await check();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function runTest() {
    setTest("Calling the AI…");
    const r = await api.aiTest();
    setTest(r.ok ? `${r.backend} answered in ${r.seconds}s: ${JSON.stringify(r.answer)}` : `Failed${r.backend ? ` (${r.backend})` : ""}: ${r.detail}`);
  }

  const dirty = JSON.stringify(ai) !== JSON.stringify(saved);
  const set = (patch: Partial<AiSettings>) => ai && setAi({ ...ai, ...patch });

  return (
    <div className="page settings">
      <header className="topbar">
        <a href="#/">← Stories</a>
        <h1>Settings</h1>
      </header>
      {error && <p className="error">{error}</p>}

      <section className="card stack">
        <h2>AI for playthroughs</h2>
        <p className="muted small">
          The AI writes AI lines, picks values for story variables from the audience's messages, and keeps story memory and
          live profiles. When it's off, slow or unavailable, the default lines play.
        </p>
        {ai && (
          <>
            <div className="backend-list">
              {BACKENDS.map((b) => {
                const avail = status?.backends.find((x) => x.backend === b.value);
                return (
                  <label key={b.value} className={`backend ${ai.backend === b.value ? "on" : ""}`}>
                    <input type="radio" name="backend" checked={ai.backend === b.value} onChange={() => set({ backend: b.value })} />
                    <span>
                      <strong>{b.label}</strong>
                      {avail && <span className={`badge ${avail.ok ? "ok" : "error"}`}>{avail.ok ? "ready" : "not ready"}</span>}
                      <span className="muted small"> {b.note}</span>
                      {avail && !avail.ok && <span className="small detail">{avail.detail}</span>}
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="grid-2">
              <label>
                Ollama address
                <input value={ai.ollama_url} onChange={(e) => set({ ollama_url: e.target.value })} />
              </label>
              <label>
                Ollama model
                <input value={ai.ollama_model} onChange={(e) => set({ ollama_model: e.target.value })} />
              </label>
              <label>
                Claude model (blank = CLI default)
                <input value={ai.claude_model} placeholder="e.g. haiku" onChange={(e) => set({ claude_model: e.target.value })} />
              </label>
              <label>
                Codex model (blank = CLI default)
                <input value={ai.codex_model} onChange={(e) => set({ codex_model: e.target.value })} />
              </label>
              <label>
                Give up after (seconds)
                <input type="number" min={2} max={300} value={ai.timeout_s} onChange={(e) => set({ timeout_s: Number(e.target.value) || 30 })} />
              </label>
            </div>
            <div className="inline">
              <button className="primary" disabled={!dirty} onClick={save}>
                Save
              </button>
              <button disabled={checking} onClick={check}>
                {checking ? "Checking…" : "Check again"}
              </button>
              <button disabled={dirty || !status?.chosen} onClick={runTest} title="One short real call to the AI a playthrough would use">
                Test call
              </button>
            </div>
            {status && (
              <p className={status.chosen ? "" : "muted"}>
                <strong>Playthroughs will use:</strong> {status.chosen ?? "no AI"} <span className="muted small">— {status.reason}</span>
              </p>
            )}
            {test && <p className="small">{test}</p>}
          </>
        )}
      </section>

      <section className="card stack">
        <h2>Matching chat to options</h2>
        <p className="muted small">
          Word overlap works out of the box. A small local embedding model also matches by meaning, so “go inside” counts for
          “Let him in”. It runs on the CPU, so it never competes with ComfyUI for the GPU.
        </p>
        {matching && (
          <>
            <p>
              <strong>Now using:</strong> {matching.matcher} <span className="muted small">— {matching.detail}</span>
            </p>
            {matching.model && !matching.ready && (
              <button disabled={matching.downloading} onClick={() => api.downloadMatching().then(setMatching)}>
                {matching.downloading ? "Downloading…" : `Download ${matching.model} (about ${matching.size_mb ?? 67} MB)`}
              </button>
            )}
            <p className="muted small">The model comes from Hugging Face and is saved in this app's data folder. Start a new playthrough to use it.</p>
          </>
        )}
      </section>

      <section className="card stack">
        <h2>Audience on your network</h2>
        {lan?.listening ? (
          <p>
            Phones and laptops on your network can join at <code>{lan.urls[0] ?? "(no network address found)"}</code>. The Stage view
            shows a QR code.
          </p>
        ) : (
          <p className="muted">{lan?.hint}</p>
        )}
      </section>

      <section className="card stack">
        <h2>Projects folder</h2>
        <code>{settings.projects_dir}</code>
        <button className="small" onClick={onChangeFolder}>
          Change folder
        </button>
      </section>
    </div>
  );
}
