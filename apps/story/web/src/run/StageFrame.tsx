import { fileUrl } from "../api";
import type { RunSnapshot } from "./types";

/** The story as the room sees it, visual-novel style. Used by the Stage view and the Debug preview. */
export function StageFrame({
  snap,
  remaining,
  join,
}: {
  snap: RunSnapshot;
  remaining: number | null;
  join?: React.ReactNode;
}) {
  const slug = snap.slug ?? "";
  const pic = snap.picture;
  const isVideo = pic ? /\.(mp4|webm|mov)$/i.test(pic) : false;
  const line = snap.line;
  const win = snap.window;
  const thinking = snap.ai?.pending === "line";
  return (
    <section className="stage">
      {pic &&
        (isVideo ? (
          <video key={pic} src={fileUrl(slug, pic)} autoPlay muted loop />
        ) : (
          <img key={pic} src={fileUrl(slug, pic)} alt="" />
        ))}
      {snap.audio && <audio key={snap.audio} src={fileUrl(slug, snap.audio)} autoPlay />}
      {line?.portrait && !win && <img className="portrait" src={fileUrl(slug, line.portrait)} alt="" />}
      {win ? (
        <div className="stage-window">
          <div className="stage-prompt">{win.prompt || (win.kind === "choice" ? "What happens next?" : "Tell us…")}</div>
          {win.options && (
            <ol className="stage-options">
              {win.options.map((o) => (
                <li key={o.id}>{o.label}</li>
              ))}
            </ol>
          )}
          <div className="countdown">{remaining !== null ? Math.ceil(remaining) : ""}</div>
          <div className="stage-hint">Type in the chat to {win.kind === "choice" ? "choose" : "have your say"}</div>
        </div>
      ) : (
        line && (
          <div className="dialogue">
            {line.speaker_name && (
              <div className="speaker" style={{ color: line.color ?? undefined }}>
                {line.speaker_name}
              </div>
            )}
            <div className="text">{thinking ? <span className="typing">…</span> : line.text}</div>
            {line.action && !thinking && <div className="action">{line.action}</div>}
          </div>
        )
      )}
      {join}
      {snap.status === "ended" && <div className="stage-end">{snap.error ? `Stopped: ${snap.error}` : "The end"}</div>}
      {snap.status === "paused" && <div className="stage-paused">Paused</div>}
    </section>
  );
}
