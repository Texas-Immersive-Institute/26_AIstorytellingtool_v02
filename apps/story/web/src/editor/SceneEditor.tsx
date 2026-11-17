import { Fragment, type ReactNode } from "react";
import type { Beat, Scene, SceneExit, Split } from "../generated/story";
import { BeatCard, StepButtons, type StepControls } from "./BeatCard";
import { BeatSummary, ExitSummary, LaneSummary, SplitSummary } from "./compact";
import { MapCanvas, useMap } from "./MapCanvas";
import { ChoiceEditor, ConditionEditor, Select, Text } from "./fields";
import { deleteScene, idMaker, moveItem, newBeat, newChoice, newCondition, newLane, newSplit } from "./storyOps";
import { useEditor } from "./useStoryEditor";

/**
 * Beats run left to right on a zoomable map. A split branches into lanes stacked beside it,
 * which rejoin before the next step. Zoomed out, every card collapses to a summary.
 */
export function SceneEditor({ sceneId, onDeleted }: { sceneId: string; onDeleted: () => void }) {
  const { story, update } = useEditor();
  const scene = story.scenes.find((s) => s.id === sceneId);
  if (!scene) return <div className="scene-editor empty muted">Select a scene on the graph.</div>;

  const edit = (mutate: (s: Scene) => void) =>
    update((d) => {
      const s = d.scenes.find((x) => x.id === sceneId);
      if (s) mutate(s);
    });

  const controlsFor = (list: (s: Scene) => unknown[], i: number, length: number): StepControls => ({
    canMoveLeft: i > 0,
    canMoveRight: i < length - 1,
    onMove: (delta) => edit((s) => moveItem(list(s), i, delta)),
    onDelete: () => edit((s) => void list(s).splice(i, 1)),
  });

  return (
    <div className="scene-editor">
      <div className="scene-head">
        <Text className="scene-title" value={scene.title} onChange={(title) => edit((s) => void (s.title = title))} />
        <Text
          className="scene-summary"
          value={scene.summary}
          placeholder="Summary (what happens in this scene)"
          onChange={(summary) => edit((s) => void (s.summary = summary))}
        />
        {story.start_scene === scene.id ? (
          <span className="badge">start</span>
        ) : (
          <button className="small" onClick={() => update((d) => void (d.start_scene = scene.id))}>
            Start here
          </button>
        )}
        <button
          className="small danger"
          onClick={() => {
            if (confirm(`Delete scene "${scene.title}"? Paths into it are removed too.`)) {
              update((d) => deleteScene(d, scene.id));
              onDeleted();
            }
          }}
        >
          Delete scene
        </button>
      </div>

      <MapCanvas viewKey={scene.id}>
        <div className="flow">
          {scene.steps.map((step, i) => (
            <Fragment key={step.id}>
              {i > 0 && <Wire />}
              {step.kind === "beat" ? (
                <BeatStep
                  beat={step}
                  index={i}
                  controls={controlsFor((s) => s.steps, i, scene.steps.length)}
                  onChange={(mutate) => edit((s) => mutate(s.steps[i] as Beat))}
                />
              ) : (
                <SplitBlock
                  split={step}
                  controls={controlsFor((s) => s.steps, i, scene.steps.length)}
                  edit={(mutate) => edit((s) => mutate(s.steps[i] as Split))}
                />
              )}
            </Fragment>
          ))}
          {scene.steps.length > 0 && <Wire />}
          <AddButtons>
            <button onClick={() => edit((s) => void s.steps.push(newBeat(idMaker(story))))}>+ Beat</button>
            <button onClick={() => edit((s) => void s.steps.push(newSplit(idMaker(story))))} title="Stacked lanes that rejoin">
              + Split into lanes
            </button>
          </AddButtons>
          <Wire />
          <ExitStep exit={scene.exit} sceneId={scene.id} onChange={(mutate) => edit((s) => mutate(s.exit))} />
        </div>
      </MapCanvas>
    </div>
  );
}

/** The line joining two steps on the map. */
function Wire() {
  return <div className="wire" />;
}

/** Add buttons only show while cards are expanded. */
function AddButtons({ children }: { children: ReactNode }) {
  const { detail } = useMap();
  return detail === "full" ? <div className="add-step stack">{children}</div> : null;
}

function BeatStep(props: { beat: Beat; index: number; controls: StepControls; onChange: (mutate: (b: Beat) => void) => void }) {
  const { detail } = useMap();
  return detail === "full" ? <BeatCard {...props} /> : <BeatSummary beat={props.beat} index={props.index} />;
}

function ExitStep(props: { exit: SceneExit; sceneId: string; onChange: (mutate: (e: SceneExit) => void) => void }) {
  const { detail } = useMap();
  return detail === "full" ? <ExitCard {...props} /> : <ExitSummary exit={props.exit} sceneId={props.sceneId} />;
}

/** Which options or rules pick a lane, shown on the lane's label. */
export function pickedBy(split: Split, laneId: string): string {
  if (split.picked_by === "choice")
    return (split.choice?.options ?? [])
      .filter((o) => o.goes_to === laneId)
      .map((o) => o.label || "unnamed option")
      .join(" · ");
  const parts = split.rules.flatMap((r, i) => (r.goes_to === laneId ? [`rule ${i + 1}`] : []));
  if (split.otherwise === laneId) parts.push("otherwise");
  return parts.join(" · ");
}

function SplitBlock({
  split,
  controls,
  edit,
}: {
  split: Split;
  controls: StepControls;
  edit: (mutate: (s: Split) => void) => void;
}) {
  const { story } = useEditor();
  const { detail } = useMap();
  const lanes = split.lanes.map((l) => ({ value: l.id, label: l.label || l.id }));

  const addLane = () =>
    edit((s) => {
      const make = idMaker(story);
      const lane = newLane(make, `Lane ${String.fromCharCode(65 + s.lanes.length)}`);
      s.lanes.push(lane);
      if (s.picked_by === "choice" && s.choice)
        s.choice.options.push({ id: make("opt"), label: lane.label, meaning: "", goes_to: lane.id, effects: [] });
    });

  const deleteLane = (li: number) => {
    if (!confirm("Delete this lane and its beats?")) return;
    edit((s) => {
      const id = s.lanes[li].id;
      s.lanes.splice(li, 1);
      s.choice?.options.forEach((o) => o.goes_to === id && (o.goes_to = null));
      s.rules = s.rules.filter((r) => r.goes_to !== id);
      if (s.otherwise === id) s.otherwise = null;
    });
  };

  const card =
    detail === "compact" ? (
      <SplitSummary split={split} />
    ) : (
      <div className="split card" data-anchor={split.id}>
        <div className="split-head">
          <strong>Split</strong>
          <span className="muted">picked by</span>
          <StepButtons controls={controls} what="split" />
        </div>
        <div className="segmented">
          <button
            className={split.picked_by === "choice" ? "on" : ""}
            onClick={() =>
              edit((s) => {
                s.picked_by = "choice";
                s.choice ??= {
                  ...newChoice(),
                  options: s.lanes.map((l) => ({ id: idMaker(story)("opt"), label: l.label, meaning: "", goes_to: l.id, effects: [] })),
                };
              })
            }
          >
            Audience choice
          </button>
          <button
            className={split.picked_by === "variable" ? "on" : ""}
            onClick={() =>
              edit((s) => {
                s.picked_by = "variable";
                s.otherwise ??= s.lanes.at(-1)?.id ?? null;
              })
            }
          >
            Story variable
          </button>
        </div>
        {split.picked_by === "choice" && split.choice ? (
          <ChoiceEditor
            value={split.choice}
            targets={lanes}
            targetLabel="lane"
            onChange={(choice) => edit((s) => void (s.choice = choice))}
          />
        ) : (
          <div className="stack">
            {split.rules.map((rule, i) => (
              <div className="stack rule" key={i}>
                <div className="inline">
                  <span className="muted">if</span>
                  <ConditionEditor value={rule.when} onChange={(when) => edit((s) => void (s.rules[i].when = when))} />
                </div>
                <div className="inline">
                  <span className="muted">→</span>
                  <Select value={rule.goes_to} options={lanes} onChange={(v) => edit((s) => void (s.rules[i].goes_to = v ?? ""))} />
                  <button className="icon" onClick={() => edit((s) => void s.rules.splice(i, 1))}>
                    ✕
                  </button>
                </div>
              </div>
            ))}
            <button
              className="small"
              disabled={!story.variables.length}
              onClick={() => edit((s) => void s.rules.push({ when: newCondition(story), goes_to: s.lanes[0]?.id ?? "" }))}
            >
              + rule
            </button>
            <div className="inline">
              <span className="muted">otherwise →</span>
              <Select value={split.otherwise} options={lanes} empty="lane…" onChange={(v) => edit((s) => void (s.otherwise = v))} />
            </div>
          </div>
        )}
        <button className="small" onClick={addLane}>
          + lane
        </button>
      </div>
    );

  return (
    <>
      {card}
      <Wire />
      <div className="fork">
        {split.lanes.map((lane, li) => {
          const via = pickedBy(split, lane.id);
          return (
            <div className="fork-lane" key={lane.id}>
              {detail === "compact" ? (
                <LaneSummary lane={lane} via={via} />
              ) : (
                <div className="lane-chip card" data-anchor={lane.id}>
                  {via && <span className="lane-via">{via}</span>}
                  <Text value={lane.label} placeholder="Lane name" onChange={(label) => edit((s) => void (s.lanes[li].label = label))} />
                  <button className="icon" title="Delete lane" disabled={split.lanes.length <= 2} onClick={() => deleteLane(li)}>
                    ✕
                  </button>
                </div>
              )}
              {lane.beats.map((beat, bi) => (
                <Fragment key={beat.id}>
                  <Wire />
                  <BeatStep
                    beat={beat}
                    index={bi}
                    controls={{
                      canMoveLeft: bi > 0,
                      canMoveRight: bi < lane.beats.length - 1,
                      onMove: (delta) => edit((s) => moveItem(s.lanes[li].beats, bi, delta)),
                      onDelete: () => edit((s) => void s.lanes[li].beats.splice(bi, 1)),
                    }}
                    onChange={(mutate) => edit((s) => mutate(s.lanes[li].beats[bi]))}
                  />
                </Fragment>
              ))}
              {detail === "full" && (
                <>
                  <Wire />
                  <button className="add-inline" onClick={() => edit((s) => void s.lanes[li].beats.push(newBeat(idMaker(story))))}>
                    + Beat
                  </button>
                </>
              )}
              <div className="lane-tail" />
            </div>
          );
        })}
      </div>
    </>
  );
}

function ExitCard({
  exit,
  sceneId,
  onChange,
}: {
  exit: SceneExit;
  sceneId: string;
  onChange: (mutate: (e: SceneExit) => void) => void;
}) {
  const { story } = useEditor();
  const scenes = story.scenes.map((s) => ({ value: s.id, label: s.id === sceneId ? `${s.title} (this scene)` : s.title }));
  const kinds = [
    { value: "next" as const, label: "Go to a scene" },
    { value: "choice" as const, label: "Audience choice" },
    { value: "variable" as const, label: "By story variable" },
    { value: "end" as const, label: "End of story" },
  ];
  return (
    <div className="exit card" data-anchor="exit">
      <strong>Then</strong>
      <Select
        value={exit.kind}
        options={kinds}
        onChange={(kind) =>
          onChange((e) => {
            if (!kind) return;
            e.kind = kind;
            if (kind === "choice") e.choice ??= newChoice();
          })
        }
      />
      {exit.kind === "next" && (
        <Select value={exit.goes_to} options={scenes} empty="scene…" onChange={(v) => onChange((e) => void (e.goes_to = v))} />
      )}
      {exit.kind === "choice" && exit.choice && (
        <ChoiceEditor
          value={exit.choice}
          targets={scenes}
          targetLabel="scene"
          onChange={(choice) => onChange((e) => void (e.choice = choice))}
        />
      )}
      {exit.kind === "variable" && (
        <div className="stack">
          {exit.rules.map((rule, i) => (
            <div className="stack rule" key={i}>
              <div className="inline">
                <span className="muted">if</span>
                <ConditionEditor value={rule.when} onChange={(when) => onChange((e) => void (e.rules[i].when = when))} />
              </div>
              <div className="inline">
                <span className="muted">→</span>
                <Select value={rule.goes_to} options={scenes} onChange={(v) => onChange((e) => void (e.rules[i].goes_to = v ?? ""))} />
                <button className="icon" onClick={() => onChange((e) => void e.rules.splice(i, 1))}>
                  ✕
                </button>
              </div>
            </div>
          ))}
          <button
            className="small"
            disabled={!story.variables.length}
            onClick={() => onChange((e) => void e.rules.push({ when: newCondition(story), goes_to: "" }))}
          >
            + rule
          </button>
          <div className="inline">
            <span className="muted">otherwise →</span>
            <Select value={exit.otherwise} options={scenes} empty="scene…" onChange={(v) => onChange((e) => void (e.otherwise = v))} />
          </div>
        </div>
      )}
    </div>
  );
}
