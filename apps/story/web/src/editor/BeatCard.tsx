import { useState } from "react";
import type { Beat, Line } from "../generated/story";
import { Area, ConditionToggle, EffectsEditor, MediaSlotEditor, Num, Select, Text } from "./fields";
import { idMaker, newLine } from "./storyOps";
import { useEditor } from "./useStoryEditor";

export interface StepControls {
  onMove: (delta: number) => void;
  onDelete: () => void;
  canMoveLeft: boolean;
  canMoveRight: boolean;
}

export function BeatCard({
  beat,
  index,
  onChange,
  controls,
}: {
  beat: Beat;
  index: number;
  onChange: (mutate: (b: Beat) => void) => void;
  controls: StepControls;
}) {
  const { story } = useEditor();
  const [more, setMore] = useState(Boolean(beat.visible_when || beat.effects.length || beat.duration_s));
  const speakers = story.characters.map((c) => ({ value: c.id, label: c.name }));
  const variables = story.variables.map((v) => ({ value: v.name, label: v.name }));

  const setLine = (i: number, patch: Partial<Line>) => onChange((b) => Object.assign(b.lines[i], patch));

  return (
    <div className={`beat card${beat.visible_when ? " conditional" : ""}`} data-anchor={beat.id}>
      <div className="beat-head">
        <span className="beat-num">{index + 1}</span>
        <Text
          value={beat.title}
          placeholder="Beat"
          className="beat-title"
          onChange={(title) => onChange((b) => void (b.title = title))}
        />
        <StepButtons controls={controls} what="beat" />
      </div>

      <MediaSlotEditor
        label="Picture"
        kinds={["picture", "video"]}
        value={beat.picture}
        onChange={(picture) => onChange((b) => void (b.picture = picture))}
      />
      <MediaSlotEditor
        label="Audio"
        kinds={["audio"]}
        value={beat.audio}
        onChange={(audio) => onChange((b) => void (b.audio = audio))}
      />

      {beat.influence && (
        <div className="influence stack">
          <div className="inline">
            <strong>Influence window</strong>
            <button className="icon" title="Remove influence window" onClick={() => onChange((b) => void (b.influence = null))}>
              ✕
            </button>
          </div>
          <Text
            value={beat.influence.prompt}
            placeholder="What the audience is asked"
            onChange={(prompt) => onChange((b) => void (b.influence!.prompt = prompt))}
          />
          <label className="inline">
            Open for
            <Num
              value={beat.influence.duration_s}
              min={1}
              onChange={(v) => onChange((b) => void (b.influence!.duration_s = v ?? 30))}
            />
            s
          </label>
          <label className="inline">
            Fills
            <Select
              value={beat.influence.fills_variable}
              options={variables}
              empty="no variable (dialogue only)"
              onChange={(v) => onChange((b) => void (b.influence!.fills_variable = v))}
            />
          </label>
        </div>
      )}

      <div className="lines stack">
        {beat.lines.map((line, i) => (
          <div key={line.id} className={`line ${line.kind}`}>
            <div className="inline">
              <Select
                value={line.speaker}
                options={speakers}
                empty="Narrator"
                onChange={(speaker) => setLine(i, { speaker })}
              />
              <div className="segmented">
                <button className={line.kind === "authored" ? "on" : ""} onClick={() => setLine(i, { kind: "authored" })}>
                  Written
                </button>
                <button className={line.kind === "ai" ? "on" : ""} onClick={() => setLine(i, { kind: "ai" })}>
                  AI
                </button>
              </div>
              <button
                className="icon"
                title="Move line up"
                disabled={i === 0}
                onClick={() => onChange((b) => b.lines.splice(i - 1, 0, ...b.lines.splice(i, 1)))}
              >
                ↑
              </button>
              <button className="icon" title="Remove line" onClick={() => onChange((b) => void b.lines.splice(i, 1))}>
                ✕
              </button>
            </div>
            {line.kind === "ai" && (
              <Area
                value={line.intent}
                placeholder="Intent: what this line should do (the AI writes it)"
                onChange={(intent) => setLine(i, { intent })}
              />
            )}
            <Area
              value={line.text}
              placeholder={line.kind === "ai" ? "Default line (plays when the AI isn't used)" : "Line"}
              onChange={(text) => setLine(i, { text })}
            />
            <Text value={line.action} placeholder="Action / stage direction" onChange={(action) => setLine(i, { action })} />
          </div>
        ))}
        <div className="inline">
          <button className="small" onClick={() => onChange((b) => void b.lines.push(newLine(idMaker(story))))}>
            + written line
          </button>
          <button className="small" onClick={() => onChange((b) => void b.lines.push(newLine(idMaker(story), "ai")))}>
            + AI line
          </button>
          {!beat.influence && (
            <button
              className="small"
              onClick={() => onChange((b) => void (b.influence = { prompt: "", duration_s: 30, fills_variable: null }))}
            >
              + influence window
            </button>
          )}
        </div>
      </div>

      <button className="link more" onClick={() => setMore(!more)}>
        {more ? "▾" : "▸"} timing, condition, effects
      </button>
      {more && (
        <div className="stack">
          <label className="inline">
            Duration
            <Num
              value={beat.duration_s}
              min={0.5}
              step={0.5}
              placeholder="auto"
              onChange={(v) => onChange((b) => void (b.duration_s = v))}
            />
            s
          </label>
          <ConditionToggle
            label="only play if"
            value={beat.visible_when}
            onChange={(c) => onChange((b) => void (b.visible_when = c))}
          />
          <span className="muted">When this beat plays:</span>
          <EffectsEditor value={beat.effects} onChange={(effects) => onChange((b) => void (b.effects = effects))} />
        </div>
      )}
    </div>
  );
}

export function StepButtons({ controls, what }: { controls: StepControls; what: string }) {
  return (
    <span className="step-buttons">
      <button className="icon" title={`Move ${what} left`} disabled={!controls.canMoveLeft} onClick={() => controls.onMove(-1)}>
        ◀
      </button>
      <button className="icon" title={`Move ${what} right`} disabled={!controls.canMoveRight} onClick={() => controls.onMove(1)}>
        ▶
      </button>
      <button
        className="icon"
        title={`Delete ${what}`}
        onClick={() => {
          if (confirm(`Delete this ${what}?`)) controls.onDelete();
        }}
      >
        🗑
      </button>
    </span>
  );
}
