import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatState, RunSnapshot } from "./types";

interface Versioned {
  epoch: number;
  version: number;
}

/** Keep the newer of two snapshots; a different epoch means the server restarted. */
export function newer<T extends Versioned>(prev: T | null, next: T): T {
  if (!prev || prev.epoch !== next.epoch || next.version >= prev.version) return next;
  return prev;
}

/** Live state from a server event stream, plus a local clock for countdowns. */
export function useLive<T extends Versioned>(url: string, remainingOf: (s: T) => number | null | undefined) {
  const [snap, setRaw] = useState<T | null>(null);
  const [connected, setConnected] = useState(true);
  const received = useRef(performance.now());
  const [, setTick] = useState(0);

  const setSnap = useCallback((next: T) => {
    setRaw((prev) => {
      const kept = newer(prev, next);
      if (kept === next) received.current = performance.now();
      return kept;
    });
  }, []);

  useEffect(() => {
    const source = new EventSource(url);
    source.onmessage = (e) => {
      setConnected(true);
      setSnap(JSON.parse(e.data) as T);
    };
    source.onerror = () => setConnected(false); // EventSource reconnects by itself
    const timer = window.setInterval(() => setTick((n) => n + 1), 200);
    return () => {
      source.close();
      window.clearInterval(timer);
    };
  }, [url, setSnap]);

  /** Seconds left on the current wait, counting down locally between server updates. */
  const remaining = (running: boolean) => {
    const left = snap ? remainingOf(snap) : null;
    if (left === null || left === undefined) return null;
    if (!running) return left;
    return Math.max(0, left - (performance.now() - received.current) / 1000);
  };

  return { snap, setSnap, remaining, connected };
}

/** The operator's full view of the running playthrough (host only). */
export function useRun() {
  const live = useLive<RunSnapshot>("/api/v1/run/stream", (s) => s.wait?.remaining);
  return { ...live, remaining: () => live.remaining(live.snap?.status === "running") };
}

/** The audience's view (any LAN device). */
export function useChat() {
  const live = useLive<ChatState>("/api/v1/chat/stream", (s) => s.window?.remaining);
  return { ...live, remaining: () => live.remaining(live.snap?.status === "running") };
}
