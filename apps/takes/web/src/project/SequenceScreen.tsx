import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, videoUrl, type Project } from "../api";
import { go } from "../route";
import { clock, sequenceOf, takeLabel, type SequenceEntry } from "./defaults";

/**
 * The sequence: every shot's selected take, played back to back in shot order. Shots with no
 * finished selected take are skipped. The next take loads while the current one plays, so the
 * cut is quick; a take with an in-point (a low-res extension) starts there (ADR-0004).
 */
export function SequenceScreen({ slug }: { slug: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [at, setAt] = useState(0); // index into `playable`
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const videos = useRef(new Map<number, HTMLVideoElement>());

  useEffect(() => {
    api.project(slug).then(
      (out) => setProject(out.project),
      (e: Error) => setError(e.message),
    );
  }, [slug]);

  const entries = useMemo(() => (project ? sequenceOf(project.shots) : []), [project]);
  const playable = useMemo(() => entries.filter((e): e is SequenceEntry & { take: NonNullable<SequenceEntry["take"]> } => !!e.take), [entries]);
  const total = playable.reduce((sum, e) => sum + (e.length_s ?? 0), 0);
  const current = playable[at];

  const jump = useCallback(
    (index: number, play = playing) => {
      if (index < 0 || index >= playable.length) return;
      setEnded(false);
      setAt(index);
      if (play) setPlaying(true);
      const video = videos.current.get(index);
      if (video) {
        video.currentTime = playable[index].from_s;
        if (play) video.play().catch(() => setPlaying(false));
      }
    },
    [playable, playing],
  );

  // When the current take changes while playing, start it (it may already be loaded as "next").
  useEffect(() => {
    const video = videos.current.get(at);
    if (video && playing && video.paused) video.play().catch(() => setPlaying(false));
  }, [at, playing]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowRight") jump(at + 1);
      else if (e.key === "ArrowLeft") jump(at - 1);
      else if (e.key === " ") {
        e.preventDefault();
        toggle();
      } else if (e.key === "f" || e.key === "F") fullscreen();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function toggle() {
    const video = videos.current.get(at);
    if (!video) return;
    if (ended) {
      playFromStart();
    } else if (video.paused) {
      video.play().catch(() => setPlaying(false));
    } else {
      video.pause();
    }
  }

  function playFromStart() {
    setEnded(false);
    setPlaying(true);
    if (at === 0) {
      const video = videos.current.get(0);
      if (video) {
        video.currentTime = playable[0].from_s;
        video.play().catch(() => setPlaying(false));
      }
    } else {
      setAt(0);
    }
  }

  function next(index: number) {
    if (index !== at) return;
    if (at + 1 < playable.length) {
      setAt(at + 1);
    } else {
      setPlaying(false);
      setEnded(true);
    }
  }

  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else stage.current?.requestFullscreen?.().catch(() => undefined);
  }

  const back = () => go({ name: "project", slug, shot: current?.shot.id ?? null });

  if (!project) {
    return <div className="centered">{error ? <span className="error">{error}</span> : "Loading…"}</div>;
  }

  return (
    <div className="sequence">
      <header className="topbar bar">
        <button onClick={back}>← Shots</button>
        <h1 className="sequence-title">
          {project.title} <span className="muted">· Sequence</span>
        </h1>
        <span className="muted">
          {playable.length} of {entries.length} shots · about {clock(total)}
        </span>
      </header>

      {playable.length === 0 ? (
        <div className="centered sequence-empty">
          <p>No shot has a selected take yet. Choose a take with ★ in each shot, then come back.</p>
          <button onClick={back}>← Back to the shots</button>
        </div>
      ) : (
        <>
          <div className="sequence-stage" ref={stage} onDoubleClick={fullscreen}>
            {playable.map((entry, i) =>
              i === at || i === at + 1 ? (
                <video
                  key={entry.take.id}
                  ref={(el) => {
                    if (el) videos.current.set(i, el);
                    else videos.current.delete(i);
                  }}
                  className={i === at ? "on" : "next"}
                  src={videoUrl(slug, entry.take.id) + (entry.from_s ? `#t=${entry.from_s}` : "")}
                  preload="auto"
                  playsInline
                  controls={i === at}
                  onLoadedMetadata={(e) => {
                    if (entry.from_s && e.currentTarget.currentTime < entry.from_s) e.currentTarget.currentTime = entry.from_s;
                  }}
                  onPlay={() => i === at && setPlaying(true)}
                  onPause={(e) => i === at && !e.currentTarget.ended && setPlaying(false)}
                  onEnded={() => next(i)}
                />
              ) : null,
            )}
            {!playing && (
              <button className="sequence-overlay primary" onClick={ended ? playFromStart : toggle}>
                {ended ? "↺ Play again" : at === 0 ? "▶ Play sequence" : "▶ Continue"}
              </button>
            )}
          </div>

          <div className="sequence-controls">
            <button onClick={() => jump(at - 1)} disabled={at === 0} title="Previous shot (←)">
              ⏮
            </button>
            <button className="primary" onClick={toggle} title="Play / pause (space)">
              {playing ? "⏸ Pause" : ended ? "↺ Play again" : "▶ Play"}
            </button>
            <button onClick={() => jump(at + 1)} disabled={at + 1 >= playable.length} title="Next shot (→)">
              ⏭
            </button>
            <span className="sequence-now">
              Shot {current.number} · {current.shot.title || "Untitled"} · {takeLabel(current.shot, current.take)}
              {current.take.upscaled && <span className="badge up">⬆ Upscaled</span>}
            </span>
            <button onClick={fullscreen} title="Full screen (F)">
              ⛶ Full screen
            </button>
          </div>

          <ol className="sequence-strip">
            {entries.map((entry) => {
              const index = playable.findIndex((p) => p.shot.id === entry.shot.id);
              return (
                <li key={entry.shot.id}>
                  <button
                    className={`${index === at ? "on" : ""} ${index < 0 ? "skipped" : ""}`}
                    disabled={index < 0}
                    onClick={() => jump(index, true)}
                    title={index < 0 ? "No selected take: skipped" : "Play from this shot"}
                  >
                    <span className="n">{entry.number}</span>
                    <span className="t">{entry.shot.title || "Untitled"}</span>
                    <span className="d">
                      {entry.take ? (entry.length_s != null ? clock(entry.length_s) : "") : "skipped"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}
