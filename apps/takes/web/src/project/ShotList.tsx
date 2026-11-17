import { useState } from "react";
import type { Shot } from "../api";
import { isUnfinished, takeLabel } from "./defaults";
import { moveItem } from "./order";

/** The sequence: shots in order. Drag a shot to move it. */
export function ShotList({
  shots,
  current,
  onOpen,
  onReorder,
  onAdd,
}: {
  shots: Shot[];
  current: string | null;
  onOpen: (id: string) => void;
  onReorder: (ids: string[]) => void;
  onAdd: () => void;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropAt, setDropAt] = useState<number | null>(null);

  function clear() {
    setDragging(null);
    setDropAt(null);
  }

  function drop() {
    if (dragging !== null && dropAt !== null && dropAt !== dragging && dropAt !== dragging + 1) {
      onReorder(moveItem(shots.map((s) => s.id), dragging, dropAt));
    }
    clear();
  }

  return (
    <aside className="shots">
      <h2>Shots</h2>
      <ol onDragEnd={clear} onDrop={(e) => (e.preventDefault(), drop())}>
        {shots.map((shot, i) => {
          const selected = shot.takes.find((t) => t.id === shot.selected_take);
          const busy = shot.takes.filter((t) => isUnfinished(t.status)).length;
          return (
            <li
              key={shot.id}
              draggable
              className={[
                shot.id === current ? "current" : "",
                dragging === i ? "dragging" : "",
                dropAt === i && dragging !== null ? "drop-before" : "",
                dropAt === i + 1 && i === shots.length - 1 && dragging !== null ? "drop-after" : "",
              ].join(" ")}
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", shot.id);
                setDragging(i);
              }}
              onDragOver={(e) => {
                if (dragging === null) return;
                e.preventDefault();
                const box = e.currentTarget.getBoundingClientRect();
                setDropAt(e.clientY < box.top + box.height / 2 ? i : i + 1);
              }}
              onClick={() => onOpen(shot.id)}
            >
              <span className="num">{i + 1}</span>
              <span className="shot-text">
                <span className="shot-title">{shot.title}</span>
                <span className="shot-meta">
                  {shot.takes.length === 0
                    ? "No takes yet"
                    : selected
                      ? `${takeLabel(shot, selected)}${selected.upscaled ? " ⬆" : ""} of ${shot.takes.length}`
                      : `${shot.takes.length} ${shot.takes.length === 1 ? "take" : "takes"}, none chosen`}
                </span>
              </span>
              {busy > 0 && <span className="spinner" title={`${busy} rendering or waiting`} />}
            </li>
          );
        })}
      </ol>
      <button onClick={onAdd}>+ Add shot</button>
    </aside>
  );
}
