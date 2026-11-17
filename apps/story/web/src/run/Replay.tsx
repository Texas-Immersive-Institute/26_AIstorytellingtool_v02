import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { href } from "../route";
import { Splitter, usePaneSize } from "../Splitter";
import { nextOf, previousOf, replayAt, type PlaythroughRecord } from "./replayState";
import { describeEvent } from "./Runner";
import { StageFrame } from "./StageFrame";

const SCENES = ["scene_entered"];
const DECISIONS = ["window_opened", "window_closed"];
const SPEEDS = [1, 2, 4, 8];
const MAX_GAP_S = 6; // when playing, a long quiet stretch waits at most this long (before speed-up)

/**
 * Step through a saved playthrough in the Debug view's layout: the stage preview and everything
 * the engine weighed, as they were after each event. Read only; the saved file never changes.
 */
export function Replay({ slug, playthrough }: { slug: string; playthrough: string }) {
  const [record, setRecord] = useState<PlaythroughRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [at, setAt] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [panelWidth, setPanelWidth, resetPanelWidth] = usePaneSize("operator", 420, 280, 1000);
  const current = useRef<HTMLLIElement>(null);
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    api.playthrough(slug, playthrough).then(setRecord, (e: Error) => setError(e.message));
  }, [slug, playthrough]);

  const events = record?.events ?? [];
  const last = Math.max(0, events.length - 1);
  const state = useMemo(() => (record ? replayAt(record, slug, at) : null), [record, slug, at]);
  const go = (k: number | null) => k !== null && setAt(Math.min(last, Math.max(0, k)));

  // Play: move to the next event after the time between them (sped up, long waits shortened).
  useEffect(() => {
    if (!playing || !record) return;
    if (at >= last) {
      setPlaying(false);
      return;
    }
    const gap = Math.min(MAX_GAP_S, Math.max(0, events[at + 1].t - events[at].t));
    const timer = window.setTimeout(() => setAt(at + 1), (gap / speed) * 1000);
    return () => window.clearTimeout(timer);
  }, [playing, at, speed, record, last, events]);

  // Keep the current event in view inside the event list only (not the whole panel).
  useEffect(() => {
    const li = current.current;
    const ol = list.current;
    if (li && ol) ol.scrollTop = li.offsetTop - ol.clientHeight / 2; // the list is li's offsetParent
  }, [at]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "ArrowRight") go(e.shiftKey ? nextOf(events, at, SCENES) : at + 1);
      else if (e.key === "ArrowLeft") go(e.shiftKey ? previousOf(events, at, SCENES) : at - 1);
      else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!record || !state) {
    return <div className="centered">{error ? <span className="error">{error}</span> : "Loading…"}</div>;
  }

  const event = events[at];
  const total = events[last]?.t ?? 0;
  const win = state.window;
  const decision = state.decision;
  const shownMessages = (state.messages ?? []).filter((m) => (win ? m.window_id === win.id : true)).slice(win ? 0 : -8);
  const maxTotal = Math.max(0.001, ...(decision?.totals?.map((o) => o.total) ?? [0]));

  return (
    <div className="runner replay">
      <header className="editor-top">
        <a href={href({ name: "run", slug })}>← Saved playthroughs</a>
        <h1>
          {record.story.title} <span className="muted">· {new Date(record.started_at).toLocaleString()}</span>
        </h1>
        <span className="badge">{record.mode === "outline_only" ? "outline only" : "live"}</span>
        {!record.ended && <span className="badge paused">unfinished</span>}
      </header>

      <div className="replay-bar">
        <button onClick={() => go(0)} disabled={at === 0} title="Start">
          ⏮
        </button>
        <button onClick={() => go(previousOf(events, at, SCENES))} disabled={previousOf(events, at, SCENES) === null} title="Previous scene (shift ←)">
          ◀ Scene
        </button>
        <button onClick={() => go(at - 1)} disabled={at === 0} title="Previous event (←)">
          ‹
        </button>
        <button className="primary" onClick={() => setPlaying(!playing)} disabled={at >= last && !playing} title="Play (space)">
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <button onClick={() => go(at + 1)} disabled={at >= last} title="Next event (→)">
          ›
        </button>
        <button onClick={() => go(nextOf(events, at, SCENES))} disabled={nextOf(events, at, SCENES) === null} title="Next scene (shift →)">
          Scene ▶
        </button>
        <button onClick={() => go(nextOf(events, at, DECISIONS))} disabled={nextOf(events, at, DECISIONS) === null} title="Next choice point or influence window">
          Next window ▶
        </button>
        <button onClick={() => go(last)} disabled={at >= last} title="End">
          ⏭
        </button>
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} title="Playback speed">
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              ×{s}
            </option>
          ))}
        </select>
        <input
          className="replay-scrub"
          type="range"
          min={0}
          max={last}
          value={at}
          onChange={(e) => go(Number(e.target.value))}
          aria-label="Event"
        />
        <span className="muted replay-time">
          {state.elapsed?.toFixed(1)} s / {total.toFixed(1)} s · event {at + 1} of {events.length}
        </span>
      </div>

      <div className="run-body" style={{ gridTemplateColumns: `1fr 0 ${panelWidth}px` }}>
        <div className="preview-col">
          <StageFrame snap={state} remaining={null} />
          <div className="join-bar">
            <strong>{event?.type}</strong> <span className="muted">{event && describeEvent(event)}</span>
          </div>
        </div>
        <Splitter axis="x" onDrag={(x) => setPanelWidth(window.innerWidth - x)} onReset={resetPanelWidth} />
        <aside className="operator">
          <section>
            <div className="inline status-line">
              <span className={`badge ${state.status}`}>{state.status}</span>
              <span>{state.scene?.title}</span>
              {state.lane_id && <span className="muted">lane {state.lane_id}</span>}
            </div>
            <div className={`ai-line ${state.ai?.enabled ? "on" : "off"}`}>
              <strong>AI:</strong> {state.ai?.enabled ? state.ai.label : "off"}
              {state.ai?.pending && <span className="badge">writing {state.ai.pending === "line" ? "a line" : "a value"}…</span>}
              {state.matcher && <span className="muted"> · matching: {state.matcher}</span>}
            </div>
            {state.error && <p className="error small">{state.error}</p>}
          </section>

          {win && (
            <section className="card">
              <strong>{win.kind === "choice" ? "Choice point" : "Influence window"} (open)</strong>
              <div className="muted">{win.prompt}</div>
              {win.options?.map((o) => (
                <div key={o.id} className="muted small">
                  · {o.label}
                </div>
              ))}
              <div className="muted small">
                {win.message_count} message(s) so far. The totals are saved when the window closes.
              </div>
            </section>
          )}
          {!win && decision && (
            <section className="card">
              <strong>{decision.kind === "choice" ? "Choice point decided" : "Influence window closed"}</strong>
              <div className="muted">{decision.prompt}</div>
              {decision.totals?.map((o) => (
                <div key={o.id} className="tally">
                  <div className="inline">
                    <span className="tally-label">
                      {o.label} {o.label === decision.chosen_label && "✓"}
                    </span>
                    <span className="muted">{o.total.toFixed(2)}</span>
                  </div>
                  <div className="bar">
                    <div style={{ width: `${(o.total / maxTotal) * 100}%` }} />
                  </div>
                </div>
              ))}
              {decision.top && (
                <ol className="top-messages">
                  {decision.top.map((m) => (
                    <li key={m.id}>
                      {m.text} <span className="muted">({m.weight.toFixed(2)})</span>
                    </li>
                  ))}
                </ol>
              )}
              <div className="muted small">
                {decision.messages} message(s) · closed by {decision.reason}
                {decision.decided_by && ` · decided by ${decision.decided_by}`}
              </div>
            </section>
          )}

          <section>
            <h3>{win ? "Messages in this window" : "Latest messages"}</h3>
            {shownMessages.length === 0 && <p className="muted small">None yet.</p>}
            <ul className="messages">
              {shownMessages.map((m) => (
                <li key={m.id} className={m.hidden ? "hidden-msg" : ""}>
                  <strong>{m.author}</strong> {m.text}{" "}
                  {Object.keys(m.scores).length > 0 && (
                    <span className="muted small">
                      [{Object.entries(m.scores).map(([k, v]) => `${k.replace(/^.*?_/, "")} ${v.toFixed(2)}`).join(", ")}]
                    </span>
                  )}
                  {m.thumbs > 0 && <span className="msg-actions">👍 {m.thumbs}</span>}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3>Story variables</h3>
            <table className="vars">
              <tbody>
                {Object.entries(state.variables ?? {}).map(([k, v]) => (
                  <tr key={k} className={event?.type === "variable_changed" && event.name === k ? "changed" : ""}>
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
              {(state.memory ?? []).map((m) => (
                <li key={m.id}>
                  <span className="badge">{m.source}</span> {m.text} {m.pinned && "📌"}
                </li>
              ))}
            </ul>
          </section>

          {Object.values(state.live_profiles ?? {}).some((notes) => notes.length > 0) && (
            <section>
              <h3>Live profiles</h3>
              <ul className="memory">
                {Object.entries(state.live_profiles ?? {}).flatMap(([who, notes]) =>
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
            <div className="muted">{(state.path ?? []).join(" → ")}</div>
          </section>

          <section>
            <h3>Events</h3>
            <ol className="events replay-events" ref={list}>
              {events.map((e, k) => (
                <li key={e.seq} ref={k === at ? current : undefined} className={k === at ? "on" : k > at ? "later" : ""} onClick={() => go(k)}>
                  <span className="muted">{e.t.toFixed(1)}s</span> <strong>{e.type}</strong> {describeEvent(e)}
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}
