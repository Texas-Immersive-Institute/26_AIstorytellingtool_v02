import { useState, type PointerEvent } from "react";

/** A pane size remembered on this computer between visits. */
export function usePaneSize(key: string, fallback: number, min: number, max: number) {
  const storageKey = `story.pane.${key}`;
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const [size, setSize] = useState(() => {
    const saved = Number(localStorage.getItem(storageKey));
    return saved ? clamp(saved) : fallback;
  });
  const set = (v: number) => {
    const next = clamp(v);
    setSize(next);
    localStorage.setItem(storageKey, String(next));
  };
  const reset = () => {
    setSize(fallback);
    localStorage.removeItem(storageKey);
  };
  return [size, set, reset] as const;
}

/**
 * A draggable edge between two panes. `onDrag` gets the pointer's page position along the axis;
 * double-click resets the size.
 */
export function Splitter({
  axis,
  onDrag,
  onReset,
}: {
  axis: "x" | "y";
  onDrag: (pos: number) => void;
  onReset: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const pos = (e: PointerEvent) => (axis === "x" ? e.clientX : e.clientY);
  return (
    <div
      className={`splitter ${axis}${dragging ? " dragging" : ""}`}
      role="separator"
      aria-orientation={axis === "x" ? "vertical" : "horizontal"}
      title="Drag to resize · double-click to reset"
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.classList.add(`resizing-${axis}`);
        setDragging(true);
      }}
      onPointerMove={(e) => dragging && onDrag(pos(e))}
      onPointerUp={(e) => {
        e.currentTarget.releasePointerCapture(e.pointerId);
        document.body.classList.remove(`resizing-${axis}`);
        setDragging(false);
      }}
      onLostPointerCapture={() => {
        document.body.classList.remove(`resizing-${axis}`);
        setDragging(false);
      }}
      onDoubleClick={onReset}
    />
  );
}
