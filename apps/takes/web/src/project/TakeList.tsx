import { useEffect, useState } from "react";
import { videoUrl, type Shot, type Take } from "../api";
import { AUDIO_LABEL, FRAMES_LABEL, STATUS_LABEL, clock, isUnfinished, takeLabel } from "./defaults";

export interface TakeActions {
  select: (t: Take) => void;
  upscale: (t: Take) => void;
  cancel: (t: Take) => void;
  remove: (t: Take) => void;
  reuse: (t: Take) => void;
}

/** The shot's player (the selected take unless you pick another to watch) and its takes, newest first. */
export function TakeList({ slug, shot, actions }: { slug: string; shot: Shot; actions: TakeActions }) {
  const [watching, setWatching] = useState<string | null>(null);
  const done = shot.takes.filter((t) => t.status === "done");
  const playing =
    done.find((t) => t.id === watching) ?? done.find((t) => t.id === shot.selected_take) ?? done[done.length - 1];

  // Watch the selected take again when it changes (e.g. an upscale arrived).
  useEffect(() => setWatching(null), [shot.selected_take]);

  return (
    <section className="takes">
      <div className="player">
        {playing ? (
          <>
            <video key={playing.id} src={videoUrl(slug, playing.id)} controls playsInline preload="metadata" />
            <p className="player-caption">
              {takeLabel(shot, playing)}
              {playing.upscaled && <span className="badge up">⬆ Upscaled</span>}
              {playing.id === shot.selected_take ? (
                <span className="badge sel">★ Plays in the sequence</span>
              ) : (
                <button onClick={() => actions.select(playing)}>★ Use this take</button>
              )}
            </p>
          </>
        ) : (
          <div className="player-empty muted">
            {shot.takes.some((t) => isUnfinished(t.status)) ? "Your first take is on its way." : "No finished takes yet."}
          </div>
        )}
      </div>

      <h3>Takes</h3>
      {shot.takes.length === 0 && <p className="muted">Generate a take with the form.</p>}
      <ul className="take-list">
        {[...shot.takes].reverse().map((take) => (
          <TakeRow
            key={take.id}
            shot={shot}
            take={take}
            playing={take.id === playing?.id}
            onWatch={() => setWatching(take.id)}
            actions={actions}
          />
        ))}
      </ul>
    </section>
  );
}

function TakeRow({
  shot,
  take,
  playing,
  onWatch,
  actions,
}: {
  shot: Shot;
  take: Take;
  playing: boolean;
  onWatch: () => void;
  actions: TakeActions;
}) {
  const unfinished = isUnfinished(take.status);
  const selected = take.id === shot.selected_take;
  const source = take.source_take ? shot.takes.find((t) => t.id === take.source_take) : undefined;
  const started = Date.parse(take.created_at);
  const ended = take.finished_at ? Date.parse(take.finished_at) : Date.now();
  const r = take.request;

  return (
    <li className={`take ${take.status} ${playing ? "playing" : ""} ${selected ? "selected" : ""}`}>
      <div className="take-head">
        {take.status === "done" ? (
          <button className="watch" onClick={onWatch} title="Watch this take">
            ▶
          </button>
        ) : (
          <span className={`dot ${take.status}`} />
        )}
        <strong>{takeLabel(shot, take)}</strong>
        {selected && <span className="badge sel">★ Selected</span>}
        {take.upscaled && <span className="badge up">⬆ Upscaled{source ? ` from ${takeLabel(shot, source)}` : ""}</span>}
        <span className={`status ${take.status}`}>
          {take.cancel_requested && unfinished ? "Cancelling…" : STATUS_LABEL[take.status]}
          {unfinished && take.status !== "queued" && ` · ${clock((Date.now() - started) / 1000)}`}
          {take.status === "done" && ` in ${clock((ended - started) / 1000)}`}
        </span>
      </div>
      <p className="take-prompt" title={r.prompt}>
        {r.prompt}
      </p>
      <p className="take-meta">
        {FRAMES_LABEL[r.frames]} · {AUDIO_LABEL[r.audio]}
        {take.duration_s ? ` · ${take.duration_s} s` : ""} · {r.aspect_ratio.replace(/ \(.*\)$/, "")}
        {take.seed !== null && ` · seed ${take.seed}`}
      </p>
      {take.error && <p className="error small">{take.error}</p>}
      <div className="take-actions">
        {take.status === "done" && !selected && <button onClick={() => actions.select(take)}>★ Select</button>}
        {take.status === "done" && !take.upscaled && <button onClick={() => actions.upscale(take)}>⬆ Upscale this take</button>}
        {!take.source_take && <button onClick={() => actions.reuse(take)}>Reuse settings</button>}
        {unfinished && !take.cancel_requested && <button onClick={() => actions.cancel(take)}>Cancel</button>}
        {!unfinished && (
          <button className="danger" onClick={() => actions.remove(take)}>
            Delete
          </button>
        )}
      </div>
    </li>
  );
}
