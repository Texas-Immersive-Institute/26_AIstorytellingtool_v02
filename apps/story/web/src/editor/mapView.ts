/** Pan and zoom maths for the beat map. A view maps map points to screen: screen = map * k + (x, y). */
export interface View {
  x: number;
  y: number;
  k: number;
}

/** How much a card shows: everything, or a short summary readable from far away. */
export type Detail = "full" | "compact";

export const MIN_ZOOM = 0.12;
export const MAX_ZOOM = 1.6;
/** Cards collapse below COLLAPSE_BELOW and expand above EXPAND_ABOVE; the gap stops flicker at the edge. */
export const COLLAPSE_BELOW = 0.55;
export const EXPAND_ABOVE = 0.65;

export const clampZoom = (k: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, k));

/** Zoom to k while keeping the map point under screen point (px, py) where it is. */
export function zoomAt(view: View, k: number, px: number, py: number): View {
  const next = clampZoom(k);
  const ratio = next / view.k;
  return { k: next, x: px - (px - view.x) * ratio, y: py - (py - view.y) * ratio };
}

export function nextDetail(current: Detail, k: number): Detail {
  if (current === "full" && k < COLLAPSE_BELOW) return "compact";
  if (current === "compact" && k > EXPAND_ABOVE) return "full";
  return current;
}

/** The view that shows the whole map (w x h at zoom 1) inside the viewport, never above zoom 1. */
export function fitView(content: { w: number; h: number }, viewport: { w: number; h: number }, pad = 24): View {
  const k = clampZoom(Math.min(1, (viewport.w - pad * 2) / content.w, (viewport.h - pad * 2) / content.h));
  return { k, x: Math.max(pad, (viewport.w - content.w * k) / 2), y: pad };
}

/** Zoom factor for one wheel event. Pinch gestures arrive as wheel events with ctrlKey and small deltas. */
export function wheelFactor(deltaY: number, deltaMode: number, pinch: boolean): number {
  const px = deltaMode === 1 ? deltaY * 16 : deltaMode === 2 ? deltaY * 400 : deltaY;
  return Math.exp(-px * (pinch ? 0.01 : 0.0015));
}
