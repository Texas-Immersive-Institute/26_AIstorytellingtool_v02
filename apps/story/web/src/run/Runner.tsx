import { useEffect, useRef, useState } from "react";
import { api, type LanInfo } from "../api";
import { href } from "../route";
import { Splitter, usePaneSize } from "../Splitter";
import { StageFrame } from "./StageFrame";
import type { PlaythroughSummary, RunEvent, RunSnapshot } from "./types";
import { useRun } from "./useRun";

/**
 * The Debug view: the operator's controls and everything the engine is weighing, with a small
 * stage preview. The room watches the Stage view (#/stage); the audience uses the Chat view.
 */
export function Runner({ slug }: { slug: string }) {
  const { snap, setSnap, remaining } = useRun();
  const [operatorWidth, setOperatorWidth, resetOperatorWidth] = usePaneSize("operator", 420, 280, 1000);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"live" | "outline_only">("live");
  const [saved, setSaved] = useState<PlaythroughSummary[]>([]);
  const mine = snap?.active && snap.slug === slug;

  useEffect(() => {
    api.playthroughs(slug).then(setSaved).catch(() => setSaved([]));
  }, [slug, snap?.status]);

  async function act<T>(fn: () => Promise<T>) {
    setError(null);
    try {
      const out = await fn();
      if (out && typeof out === "object" && "version" in out) setSnap(out as unknown as RunSnapshot);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="runner">
      <header className="editor-top">
        <a href={href({ name: "project", slug })}>← Edit story</a>
        <h1>{mine ? snap.title : "Run"}</h1>
        <a className="button" href={href({ name: "stage" })} target="_blank" rel="noreferrer" title="Open the Stage view in a new window for the projector">
          Open Stage ↗
        </a>
        {mine && snap.status !== "ended" ? (
          <button className="danger" onClick={() => act(api.stopRun)}>
            ■ Stop
          </button>
        ) : (
          <>
            <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
              <option value="live">Live (audience shapes it)</option>
              <option value="outline_only">Outline only (defaults, no AI)</option>
            </select>
            <button className="primary" onClick={() => act(() => api.startRun(slug, mode))}>
              ▶ Start playthrough
            </button>
          </>
        )}
      </header>
      {error && <p className="error banner">{error}</p>}
      {snap?.active && !mine && (
        <p className="banner muted">
          A playthrough of “{snap.title}” is running. Starting here stops it.
        </p>
      )}

      {mine ? (
        <div className="run-body" style={{ gridTemplateColumns: `1fr 0 ${operatorWidth}px` }}>
          <div className="preview-col">
            <StageFrame snap={snap} remaining={remaining()} />
            <JoinBar />
          </div>
          <Splitter
            axis="x"
            onDrag={(x) => setOperatorWidth(window.innerWidth - x)}
            onReset={resetOperatorWidth}
          />
          <Operator snap={snap} remaining={remaining()} act={act} />
        </div>
      ) : (
        <SavedList slug={slug} saved={saved} />
      )}
    </div>
  );
}

function Operator({
  snap,
  remaining,
  act,
}: {
  snap: RunSnapshot;
  remaining: number | null;
  act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [author, setAuthor] = useState("audience 1");
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const win = snap.window;
  const running = snap.status !== "ended";
  const maxTotal = Math.max(0.001, ...(win?.options?.map((o) => o.total) ?? [0]));
  const windowMessages = (snap.messages ?? []).filter((m) => win && m.window_id === win.id);

  return (
    <aside className="operator">
      <section>
        <div className="inline status-line">
          <span className={`badge ${snap.status}`}>{snap.status}</span>
          <span>{snap.scene?.title}</span>
          {snap.lane_id && <span className="muted">lane {snap.lane_id}</span>}
          <span className="muted">
            {snap.wait?.kind} {remaining !== null && `· ${remaining.toFixed(1)}s`}
          </span>
          {snap.mode === "outline_only" && <span className="badge">outline only</span>}
        </div>
        <div className={`ai-line ${snap.ai?.enabled ? "on" : "off"}`} title={snap.ai?.reason}>
          <strong>AI:</strong> {snap.ai?.enabled ? snap.ai.label : "off"}
          {snap.ai?.pending && <span className="badge">writing {snap.ai.pending === "line" ? "a line" : "a value"}…</span>}
          {snap.ai?.enabled && !snap.has_audience_input && <span className="muted"> · waits for the first audience message</span>}
          <span className="muted"> · matching: {snap.matcher}</span>
          {!snap.ai?.enabled && snap.ai?.reason && <div className="muted small">{snap.ai.reason}</div>}
        </div>
        <div className="inline">
          {snap.status === "paused" ? (
            <button disabled={!running} onClick={() => act(() => api.control("resume"))}>
              ▶ Resume
            </button>
          ) : (
            <button disabled={!running} onClick={() => act(() => api.control("pause"))}>
              ❚❚ Pause
            </button>
          )}
          <button disabled={!running || win?.kind === "choice"} onClick={() => act(() => api.control("skip"))}>
            Skip ⏭
          </button>
          <button disabled={!win} onClick={() => act(() => api.control("close_window"))}>
            Close now
          </button>
          <button disabled={!win} onClick={() => act(() => api.control("add_time", { seconds: 15 }))}>
            +15 s
          </button>
        </div>
      </section>

      {win && (
        <section className="card">
          <strong>{win.kind === "choice" ? "Choice point" : "Influence window"}</strong>
          <div className="muted">{win.prompt}</div>
          {win.options?.map((o) => (
            <div key={o.id} className="tally">
              <div className="inline">
                <span className="tally-label">{o.label}</span>
                <span className="muted">
                  {o.total.toFixed(2)} · {o.messages} msg
                </span>
                <button className="small" title="Pick this option now" onClick={() => act(() => api.control("force_option", { option_id: o.id }))}>
                  Pick
                </button>
              </div>
              <div className="bar">
                <div style={{ width: `${(o.total / maxTotal) * 100}%` }} />
              </div>
            </div>
          ))}
          {win.kind === "choice" && <div className="muted small">{win.unmatched ?? 0} unmatched message(s). No matched messages → random pick.</div>}
          {win.top && (
            <ol className="top-messages">
              {win.top.map((m) => (
                <li key={m.id}>
                  {m.text} <span className="muted">({m.weight.toFixed(2)})</span>
                </li>
              ))}
            </ol>
          )}
          {win.fills_variable && (
            <div className="muted small">
              The top message fills <code>{win.fills_variable}</code>.
            </div>
          )}
        </section>
      )}

      <section>
        <h3>Pose as the audience</h3>
        <form
          className="inline"
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            void act(() => api.say(author, text));
            setText("");
          }}
        >
          <input className="author" value={author} onChange={(e) => setAuthor(e.target.value)} />
          <input className="grow" value={text} placeholder={win ? "Type a message…" : "Messages count most while a window is open"} onChange={(e) => setText(e.target.value)} />
          <button disabled={!running}>Send</button>
        </form>
        <ul className="messages">
          {(win ? windowMessages : (snap.messages ?? []).slice(-8)).map((m) => (
            <li key={m.id} className={m.hidden ? "hidden-msg" : ""}>
              <strong>{m.author}</strong> {m.text}{" "}
              {Object.keys(m.scores).length > 0 && (
                <span className="muted small">
                  [{Object.entries(m.scores).map(([k, v]) => `${k.replace(/^.*?_/, "")} ${v.toFixed(2)}`).join(", ")}]
                </span>
              )}
              <span className="msg-actions">
                <button className="icon" title="Thumbs-up as another audience member" onClick={() => act(() => api.thumbsUp(m.id, `voter ${Math.random().toString(36).slice(2, 6)}`))}>
                  👍 {m.thumbs}
                </button>
                <button className="icon" title={m.hidden ? "Show" : "Hide"} onClick={() => act(() => api.hideMessage(m.id, !m.hidden))}>
                  {m.hidden ? "show" : "hide"}
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <Weights snap={snap} act={act} />

      <section>
        <h3>Story variables</h3>
        <table className="vars">
          <tbody>
            {Object.entries(snap.variables ?? {}).map(([k, v]) => (
              <tr key={k} className={recentlyChanged(snap.events, k) ? "changed" : ""}>
                <td>
                  <code>{k}</code>
                </td>
                <td>{JSON.stringify(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Story memory</h3>
        <ul className="memory">
          {(snap.memory ?? []).map((m) => (
            <li key={m.id}>
              <span className="badge">{m.source}</span> {m.text}
              <button className="icon" title={m.pinned ? "Unpin" : "Pin"} onClick={() => act(() => api.editMemory(m.id, { pinned: !m.pinned }))}>
                {m.pinned ? "📌" : "pin"}
              </button>
              <button className="icon" title="Delete" onClick={() => act(() => api.deleteMemory(m.id))}>
                ✕
              </button>
            </li>
          ))}
        </ul>
        <form
          className="inline"
          onSubmit={(e) => {
            e.preventDefault();
            if (!note.trim()) return;
            void act(() => api.addMemory(note));
            setNote("");
          }}
        >
          <input className="grow" value={note} placeholder="Add a memory note" onChange={(e) => setNote(e.target.value)} />
          <button disabled={!running}>Add</button>
        </form>
      </section>

      {Object.values(snap.live_profiles ?? {}).some((notes) => notes.length > 0) && (
        <section>
          <h3>Live profiles</h3>
          <ul className="memory">
            {Object.entries(snap.live_profiles ?? {}).flatMap(([who, notes]) =>
              notes.map((n, i) => (
                <li key={`${who}-${i}`}>
                  <strong>{who}</strong> {n}
                </li>
              )),
            )}
          </ul>
        </section>
      )}

      <section>
        <h3>Path</h3>
        <div className="muted">{(snap.path ?? []).join(" → ")}</div>
      </section>

      <section>
        <h3>Events</h3>
        <ol className="events" reversed>
          {[...(snap.events ?? [])].reverse().slice(0, 60).map((e) => (
            <li key={e.seq}>
              <span className="muted">{e.t.toFixed(1)}s</span> <strong>{e.type}</strong> {describeEvent(e)}
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}

/** Live weighting sliders: change how chat is weighed mid-playthrough and watch totals move. */
function Weights({ snap, act }: { snap: RunSnapshot; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const tuning = snap.tuning ?? { thumbs_up_factor: 1, match_threshold: 0.35 };
  const [local, setLocal] = useState(tuning);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => setLocal(tuning), [tuning.thumbs_up_factor, tuning.match_threshold]);

  const change = (patch: Partial<typeof tuning>) => {
    setLocal({ ...local, ...patch });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void act(() => api.tune(patch)), 150);
  };

  return (
    <section>
      <h3>Weighting</h3>
      <label className="slider">
        <span>
          Thumbs-up factor <strong>{local.thumbs_up_factor.toFixed(2)}</strong>
        </span>
        <input type="range" min={0} max={5} step={0.25} value={local.thumbs_up_factor} onChange={(e) => change({ thumbs_up_factor: Number(e.target.value) })} />
      </label>
      <label className="slider">
        <span>
          Match threshold <strong>{local.match_threshold.toFixed(2)}</strong>
        </span>
        <input type="range" min={0} max={1} step={0.05} value={local.match_threshold} onChange={(e) => change({ match_threshold: Number(e.target.value) })} />
      </label>
      <p className="muted small">weight = match score × (1 + thumbs-ups × factor). Below the threshold a message is unmatched. Changes apply to this playthrough only.</p>
    </section>
  );
}

/** Where audience devices join, shown under the stage preview. */
function JoinBar() {
  const [lan, setLan] = useState<LanInfo | null>(null);
  useEffect(() => {
    api.lan().then(setLan).catch(() => setLan(null));
  }, []);
  if (!lan) return null;
  return (
    <div className="join-bar">
      {lan.urls.length ? (
        <>
          Audience chat: <code>{lan.urls[0]}</code>
          <a href={href({ name: "chat" })} target="_blank" rel="noreferrer">
            open here ↗
          </a>
        </>
      ) : (
        <>
          <span className="muted">{lan.hint}</span>{" "}
          <a href={href({ name: "chat" })} target="_blank" rel="noreferrer">
            Open the chat on this computer ↗
          </a>
        </>
      )}
    </div>
  );
}

function SavedList({ slug, saved }: { slug: string; saved: PlaythroughSummary[] }) {
  return (
    <div className="page">
      <h2>Saved playthroughs</h2>
      {saved.length === 0 ? (
        <p className="muted">None yet. Each playthrough is saved into the project's playthroughs folder.</p>
      ) : (
        <ul className="plain-list">
          {saved.map((p) => (
            <li key={p.id} className="card">
              <strong>{new Date(p.started_at).toLocaleString()}</strong>
              <span className="muted">
                {p.mode === "outline_only" ? "outline only" : "live"} · {p.messages} message(s) · {p.ended ? "finished" : "unfinished"}
              </span>
              <span className="small">{p.path.join(" → ")}</span>
              <a className="button" href={href({ name: "replay", slug, playthrough: p.id })}>
                Step through ▶
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function recentlyChanged(events: RunEvent[] | undefined, name: string): boolean {
  const recent = (events ?? []).slice(-12);
  return recent.some((e) => e.type === "variable_changed" && e.name === name);
}

export function describeEvent(e: RunEvent): string {
  switch (e.type) {
    case "scene_entered":
      return String(e.title);
    case "line_shown":
      return `${e.source}: ${String(e.text).slice(0, 60)}`;
    case "variable_changed":
      return `${e.name}: ${JSON.stringify(e.old)} → ${JSON.stringify(e.new)} (${e.cause})`;
    case "window_opened":
      return `${e.kind}: ${e.prompt}`;
    case "window_closed":
      return e.kind === "choice" ? `→ ${e.chosen_label} (${e.decided_by})` : `${e.messages} message(s)`;
    case "message":
      return `${(e.message as { author: string; text: string }).author}: ${(e.message as { text: string }).text}`;
    case "beat_skipped":
    case "beat_entered":
      return String(e.beat_id);
    case "lane_picked":
    case "path_picked":
      return `${e.lane_id ?? e.goes_to} (by ${e.by})`;
    case "ai_requested":
      return e.kind === "line" ? `line for ${(e.context as { speaker?: string })?.speaker ?? "?"}` : `value for ${(e.context as { variable?: { name: string } })?.variable?.name}`;
    case "ai_answered":
      return `${e.backend} in ${e.seconds}s → ${JSON.stringify(e.used)}`;
    case "ai_fallback":
      return `default used: ${e.reason}`;
    case "tuned":
      return Object.entries(e)
        .filter(([k]) => !["seq", "t", "type"].includes(k))
        .map(([k, v]) => `${k} = ${v}`)
        .join(", ");
    case "live_profile_added":
      return `${e.character}: ${e.note}`;
    case "memory_added":
      return `${(e.entry as { source: string; text: string }).source}: ${(e.entry as { text: string }).text}`;
    case "error":
    case "warning":
      return String(e.message);
    default:
      return "";
  }
}
