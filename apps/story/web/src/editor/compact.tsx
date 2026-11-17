import type { MouseEvent } from "react";
import { fileUrl } from "../api";
import type { Beat, Lane, SceneExit, Split } from "../generated/story";
import { useMap } from "./MapCanvas";
import { useEditor } from "./useStoryEditor";

/** Collapsed cards for the zoomed-out beat map: large type, the gist only. Click one to zoom in on it. */

function useFocus() {
  const { focus } = useMap();
  return (e: MouseEvent<HTMLElement>) => focus(e.currentTarget);
}

const IMAGE = /\.(png|jpe?g|webp|gif|svg|avif)$/i;
const VIDEO = /\.(mp4|webm|mov|m4v)$/i;

export function BeatSummary({ beat, index }: { beat: Beat; index: number }) {
  const { story, slug } = useEditor();
  const focus = useFocus();
  const pic = beat.picture.mode === "set" ? beat.picture.asset : null;
  const first = beat.lines[0];
  const speaker = first ? (story.characters.find((c) => c.id === first.speaker)?.name ?? "Narrator") : null;
  const ai = beat.lines.filter((l) => l.kind === "ai").length;
  const meta = [
    `${beat.lines.length} line${beat.lines.length === 1 ? "" : "s"}`,
    ai ? `${ai} AI` : "",
    beat.influence ? "influence" : "",
    beat.visible_when ? "conditional" : "",
  ].filter(Boolean);

  return (
    <div
      className={`beat card compact${beat.visible_when ? " conditional" : ""}`}
      data-anchor={beat.id}
      title="Zoom in to edit"
      onClick={focus}
    >
      <div className="compact-head">
        <span className="beat-num">{index + 1}</span>
        <span className="compact-title">{beat.title || "Beat"}</span>
      </div>
      {pic && IMAGE.test(pic) ? (
        <img className="compact-thumb" src={fileUrl(slug, pic)} alt="" draggable={false} />
      ) : pic && VIDEO.test(pic) ? (
        <video className="compact-thumb" src={fileUrl(slug, pic)} muted preload="metadata" />
      ) : (
        <div className="compact-thumb empty">{beat.picture.mode === "hold" ? "picture held" : beat.picture.mode === "clear" ? "no picture" : "no file chosen"}</div>
      )}
      {first && (
        <div className="compact-line">
          <strong>{speaker}:</strong> {first.text || first.intent || "…"}
        </div>
      )}
      <div className="compact-meta">{meta.join(" · ")}</div>
    </div>
  );
}

export function SplitSummary({ split }: { split: Split }) {
  const focus = useFocus();
  const byChoice = split.picked_by === "choice";
  return (
    <div className="split card compact" data-anchor={split.id} title="Zoom in to edit" onClick={focus}>
      <div className="compact-head">
        <span className="compact-title">Split</span>
      </div>
      <div className="compact-line">
        {byChoice ? <>Audience: {split.choice?.prompt || "choice"}</> : "By story variable"}
      </div>
      <div className="compact-meta">
        {split.lanes.length} lanes{byChoice && split.choice ? ` · ${split.choice.countdown_s}s` : ""}
      </div>
    </div>
  );
}

export function LaneSummary({ lane, via }: { lane: Lane; via: string }) {
  const focus = useFocus();
  return (
    <div className="lane-chip card compact" data-anchor={lane.id} title="Zoom in to edit" onClick={focus}>
      <span className="compact-title">{lane.label || "Lane"}</span>
      {via && <span className="compact-meta">{via}</span>}
    </div>
  );
}

export function ExitSummary({ exit, sceneId }: { exit: SceneExit; sceneId: string }) {
  const { story } = useEditor();
  const focus = useFocus();
  const title = (id: string | null | undefined) => (id === sceneId ? "this scene" : (story.scenes.find((s) => s.id === id)?.title ?? "?"));
  const text =
    exit.kind === "end"
      ? "End of story"
      : exit.kind === "next"
        ? `→ ${exit.goes_to ? title(exit.goes_to) : "no scene yet"}`
        : exit.kind === "choice"
          ? `Audience: ${exit.choice?.prompt || "choice"}`
          : "By story variable";
  const targets =
    exit.kind === "choice"
      ? (exit.choice?.options ?? []).map((o) => `${o.label || "option"} → ${title(o.goes_to)}`)
      : exit.kind === "variable"
        ? [...exit.rules.map((r) => `→ ${title(r.goes_to)}`), `otherwise → ${title(exit.otherwise)}`]
        : [];
  return (
    <div className="exit card compact" data-anchor="exit" title="Zoom in to edit" onClick={focus}>
      <div className="compact-head">
        <span className="compact-title">Then</span>
      </div>
      <div className="compact-line">{text}</div>
      {targets.map((t, i) => (
        <div className="compact-meta" key={i}>
          {t}
        </div>
      ))}
    </div>
  );
}
