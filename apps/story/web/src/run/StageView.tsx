import { useEffect, useState } from "react";
import { api, qrUrl, type LanInfo } from "../api";
import { StageFrame } from "./StageFrame";
import { useRun } from "./useRun";

/**
 * The Stage view: open it on the host and put it on the projector or big screen.
 * Press F (or double-click) for full screen.
 */
export function StageView() {
  const { snap, remaining } = useRun();
  const [lan, setLan] = useState<LanInfo | null>(null);

  useEffect(() => {
    api.lan().then(setLan).catch(() => setLan(null));
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "f" || e.key === "F") toggleFullscreen();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const url = lan?.urls[0];
  const join = url ? <JoinCard url={url} big={!snap?.active || !!snap.window} /> : null;

  return (
    <div className="stage-page" onDoubleClick={toggleFullscreen}>
      {snap?.active ? (
        <StageFrame snap={snap} remaining={remaining()} join={join} />
      ) : (
        <section className="stage stage-idle">
          <div className="idle-title">The story will begin shortly</div>
          {join}
          {!url && lan?.hint && <div className="idle-hint">{lan.hint}</div>}
        </section>
      )}
    </div>
  );
}

function JoinCard({ url, big }: { url: string; big: boolean }) {
  return (
    <div className={`join-card${big ? " big" : ""}`}>
      <img src={qrUrl} alt="QR code to join the chat" />
      <div>
        <div className="join-title">Join the chat</div>
        <div className="join-url">{url.replace(/^http:\/\//, "")}</div>
      </div>
    </div>
  );
}

function toggleFullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen();
  else void document.documentElement.requestFullscreen().catch(() => undefined);
}
