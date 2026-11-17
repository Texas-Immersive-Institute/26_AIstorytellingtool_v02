import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent,
  type ReactNode,
} from "react";
import { fitView, nextDetail, wheelFactor, zoomAt, type Detail, type View } from "./mapView";

interface MapControls {
  detail: Detail;
  /** Zoom in on a card (from a collapsed card's click). */
  focus: (el: HTMLElement) => void;
}

const MapContext = createContext<MapControls>({ detail: "full", focus: () => {} });
export const useMap = () => useContext(MapContext);

/** Clicks and drags on these work as usual instead of moving the map. */
const INTERACTIVE = "input, textarea, select, button, a, label, audio, video, [contenteditable], .no-pan";
const START: View = { x: 0, y: 0, k: 1 };
/** Each scene keeps its own place on the map while the editor is open. */
const savedViews = new Map<string, View>();

interface Anchor {
  id: string;
  fx: number;
  fy: number;
  px: number;
  py: number;
}

/**
 * A pannable, zoomable surface: scroll to zoom around the cursor, drag empty space (or anywhere
 * with the middle button) to move. Cards marked with data-anchor stay under the cursor when they
 * collapse or expand, so the map does not jump.
 */
export function MapCanvas({ viewKey, children }: { viewKey: string; children: ReactNode }) {
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [view, setViewState] = useState<View>(() => savedViews.get(viewKey) ?? START);
  const [detail, setDetail] = useState<Detail>(() => nextDetail("full", view.k));
  const viewRef = useRef(view);
  const detailRef = useRef(detail);
  const anchor = useRef<Anchor | null>(null);
  const refit = useRef(false);

  const apply = (next: View) => {
    viewRef.current = next;
    savedViews.set(viewKey, next);
    setViewState(next);
  };

  /** Screen point relative to the viewport. */
  const local = (clientX: number, clientY: number) => {
    const r = viewport.current!.getBoundingClientRect();
    return { x: clientX - r.left, y: clientY - r.top };
  };

  /** The card under (or nearest to) a viewport point, and where in it that point falls. */
  const anchorAt = (px: number, py: number): Anchor | null => {
    const vp = viewport.current!.getBoundingClientRect();
    let best: { el: HTMLElement; d: number } | null = null;
    for (const el of content.current!.querySelectorAll<HTMLElement>("[data-anchor]")) {
      const r = el.getBoundingClientRect();
      const dx = Math.max(r.left - vp.left - px, 0, px - (r.right - vp.left));
      const dy = Math.max(r.top - vp.top - py, 0, py - (r.bottom - vp.top));
      const d = dx * dx + dy * dy;
      if (!best || d < best.d) best = { el, d };
    }
    if (!best) return null;
    const r = best.el.getBoundingClientRect();
    const clamp = (v: number) => Math.min(1, Math.max(0, v));
    return {
      id: best.el.dataset.anchor!,
      fx: clamp((px + vp.left - r.left) / (r.width || 1)),
      fy: clamp((py + vp.top - r.top) / (r.height || 1)),
      px,
      py,
    };
  };

  /** Change the view; if cards collapse or expand, pin the card at (px, py) so it stays put. */
  const commit = (next: View, px: number, py: number, pin?: Anchor | null) => {
    const d = nextDetail(detailRef.current, next.k);
    if (d !== detailRef.current) {
      anchor.current = pin ?? anchorAt(px, py);
      detailRef.current = d;
      setDetail(d);
    } else if (pin) {
      anchor.current = pin;
    }
    apply(next);
  };

  /** Show the whole scene. Collapsing changes the map's size, so the first fit may run again once. */
  const fit = (mayChangeDetail = true) => {
    const vp = viewport.current!;
    const c = content.current!;
    const next = fitView({ w: c.offsetWidth, h: c.offsetHeight }, { w: vp.clientWidth, h: vp.clientHeight });
    const d = nextDetail(detailRef.current, next.k);
    if (mayChangeDetail && d !== detailRef.current) {
      refit.current = true;
      detailRef.current = d;
      setDetail(d);
    }
    apply(next);
  };

  const zoomBy = (factor: number) => {
    const vp = viewport.current!;
    const cx = vp.clientWidth / 2;
    const cy = vp.clientHeight / 2;
    commit(zoomAt(viewRef.current, viewRef.current.k * factor, cx, cy), cx, cy);
  };

  const focus = (el: HTMLElement) => {
    const id = el.dataset.anchor;
    if (!id) return;
    const vp = viewport.current!;
    const r = el.getBoundingClientRect();
    const v = local(r.left + r.width / 2, r.top);
    const next = zoomAt(viewRef.current, 1, v.x, v.y);
    commit(next, v.x, v.y, { id, fx: 0.5, fy: 0, px: vp.clientWidth / 2, py: 32 });
  };

  // Restore each scene's own view when switching scenes.
  useEffect(() => {
    const v = savedViews.get(viewKey) ?? START;
    const d = nextDetail(detailRef.current, v.k);
    detailRef.current = d;
    anchor.current = null;
    setDetail(d);
    apply(v);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewKey]);

  // After a collapse/expand, move the map so the pinned card is where it was on screen.
  useLayoutEffect(() => {
    if (refit.current) {
      refit.current = false;
      anchor.current = null;
      fit(false);
      return;
    }
    const a = anchor.current;
    if (!a) return;
    anchor.current = null;
    const el = content.current?.querySelector<HTMLElement>(`[data-anchor="${CSS.escape(a.id)}"]`);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const p = local(r.left + a.fx * r.width, r.top + a.fy * r.height);
    const v = viewRef.current;
    apply({ ...v, x: v.x + (a.px - p.x), y: v.y + (a.py - p.y) });
  });

  // Wheel zoom needs a non-passive listener so the page does not scroll as well.
  useEffect(() => {
    const vp = viewport.current!;
    const onWheel = (e: WheelEvent) => {
      const area = (e.target as Element).closest("textarea, select");
      if (area && area.scrollHeight > area.clientHeight) return;
      e.preventDefault();
      const p = local(e.clientX, e.clientY);
      const v = viewRef.current;
      commit(zoomAt(v, v.k * wheelFactor(e.deltaY, e.deltaMode, e.ctrlKey), p.x, p.y), p.x, p.y);
    };
    vp.addEventListener("wheel", onWheel, { passive: false });
    return () => vp.removeEventListener("wheel", onWheel);
  });

  // Drag to move. Capture the pointer only once it really moves, so plain clicks still reach cards.
  const drag = useRef<{ id: number; sx: number; sy: number; vx: number; vy: number; moving: boolean } | null>(null);
  const onPointerDown = (e: PointerEvent) => {
    const middle = e.button === 1;
    if (!middle && e.button !== 0) return;
    if (!middle && (e.target as Element).closest(INTERACTIVE)) return;
    if (middle) e.preventDefault();
    drag.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, vx: viewRef.current.x, vy: viewRef.current.y, moving: false };
  };
  const onPointerMove = (e: PointerEvent) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (!d.moving) {
      if (Math.hypot(dx, dy) < 4) return;
      d.moving = true;
      viewport.current!.setPointerCapture(e.pointerId);
    }
    apply({ ...viewRef.current, x: d.vx + dx, y: d.vy + dy });
  };
  const onPointerUp = (e: PointerEvent) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    if (d.moving) {
      viewport.current!.releasePointerCapture(e.pointerId);
      // a drag that ends over a card must not also click it
      const swallow = (c: MouseEvent) => c.stopPropagation();
      window.addEventListener("click", swallow, { capture: true, once: true });
      window.setTimeout(() => window.removeEventListener("click", swallow, true), 0);
    }
  };

  const dots = 22 * view.k;
  return (
    <MapContext.Provider value={{ detail, focus }}>
      <div
        ref={viewport}
        className={`map-viewport${drag.current?.moving ? " panning" : ""}`}
        style={{ backgroundSize: `${dots}px ${dots}px`, backgroundPosition: `${view.x}px ${view.y}px` }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onAuxClick={(e) => e.button === 1 && e.preventDefault()}
      >
        <div
          ref={content}
          className={`map-content ${detail}`}
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, ["--k" as string]: view.k }}
        >
          {children}
        </div>
        <div className="map-toolbar no-pan">
          <button className="icon" title="Zoom out" onClick={() => zoomBy(1 / 1.25)}>
            −
          </button>
          <button className="icon zoom-level" title="Back to 100%" onClick={() => zoomBy(1 / viewRef.current.k)}>
            {Math.round(view.k * 100)}%
          </button>
          <button className="icon" title="Zoom in" onClick={() => zoomBy(1.25)}>
            +
          </button>
          <button className="small" title="Show the whole scene" onClick={() => fit()}>
            Fit
          </button>
          <span className="muted hint">Scroll to zoom · drag empty space to move</span>
        </div>
      </div>
    </MapContext.Provider>
  );
}
