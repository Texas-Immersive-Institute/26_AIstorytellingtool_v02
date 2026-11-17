import { useEffect, useState } from "react";
import { api, type ComfyStatus } from "./api";

/** Is the H3 ComfyUI ready? Checked every 15 s. */
export function useComfy(): [ComfyStatus | null, () => void] {
  const [status, setStatus] = useState<ComfyStatus | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    const load = () =>
      api
        .comfyui()
        .then((s) => live && setStatus(s))
        .catch(() => live && setStatus(null));
    load();
    const timer = window.setInterval(load, 15000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [tick]);
  return [status, () => setTick((t) => t + 1)];
}

export function ComfyBadge({ status }: { status: ComfyStatus | null }) {
  if (!status) return <span className="badge">ComfyUI: checking…</span>;
  return (
    <a
      href="#/settings"
      className={`badge ${status.ready ? "ok" : "error"}`}
      title={status.message || status.url}
    >
      {status.ready ? "ComfyUI ready" : status.reachable ? "ComfyUI: no H3 nodes" : "ComfyUI not running"}
    </a>
  );
}
