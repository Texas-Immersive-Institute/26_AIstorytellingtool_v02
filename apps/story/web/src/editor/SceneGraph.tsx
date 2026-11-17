import { useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { fileUrl } from "../api";
import type { Scene } from "../generated/story";
import { addScene, connect, sceneLinks, slugId, unlink } from "./storyOps";
import { useEditor } from "./useStoryEditor";

type SceneNodeData = { scene: Scene; isStart: boolean; errors: number; selected: boolean; thumb: string | null };
type SceneNode = Node<SceneNodeData, "scene">;

/** The first picture a scene's beats set (scenes have no picture of their own). */
export function scenePicture(scene: Scene): string | null {
  for (const step of scene.steps) {
    const beats = step.kind === "beat" ? [step] : (step.lanes[0]?.beats ?? []);
    for (const beat of beats) if (beat.picture.mode === "set" && beat.picture.asset) return beat.picture.asset;
  }
  return null;
}

const EXIT_LABEL: Record<string, string> = { next: "→", choice: "choice", variable: "by variable", end: "end" };

function SceneNodeView({ data }: NodeProps<SceneNode>) {
  const { scene, isStart, errors } = data;
  const beats = scene.steps.length;
  return (
    <div className={`scene-node${data.selected ? " selected" : ""}${scene.exit.kind === "end" ? " ending" : ""}`}>
      <Handle type="target" position={Position.Left} />
      {data.thumb && <img className="scene-node-thumb" src={data.thumb} alt="" />}
      <div className="scene-node-title">
        {isStart && <span className="badge">start</span>} {scene.title || scene.id}
      </div>
      {scene.summary && <div className="scene-node-summary">{scene.summary}</div>}
      <div className="scene-node-meta">
        <span>
          {beats} step{beats === 1 ? "" : "s"}
        </span>
        <span>{EXIT_LABEL[scene.exit.kind]}</span>
        {errors > 0 && <span className="err">⚠ {errors}</span>}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { scene: SceneNodeView };

function Graph({ selected, onSelect }: { selected: string | null; onSelect: (id: string | null) => void }) {
  const { story, issues, update, slug } = useEditor();
  const flow = useReactFlow();

  // Refit when the graph's box changes size (first layout, window resize), so scenes never
  // end up stuck at minimum zoom off to one side.
  useEffect(() => {
    const el = document.querySelector(".graph");
    if (!el) return;
    let timer: number | undefined;
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void flow.fitView({ padding: 0.2, duration: 200 }), 120);
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [flow]);

  const addAt = (x: number, y: number) => {
    const id = slugId(story, "New scene", "scene");
    update((d) => void addScene(d, Math.round(x), Math.round(y), "New scene", id));
    onSelect(id);
  };

  const thumbOf = (s: Scene) => {
    const pic = scenePicture(s);
    return pic && /\.(png|jpe?g|webp|gif|svg)$/i.test(pic) ? fileUrl(slug, pic) : null;
  };

  const errorsByScene = useMemo(() => {
    const m = new Map<string, number>();
    for (const i of issues) {
      const id = i.where.match(/^scenes\/([^/]+)/)?.[1];
      if (id && i.level === "error") m.set(id, (m.get(id) ?? 0) + 1);
    }
    return m;
  }, [issues]);

  const built = useMemo<SceneNode[]>(
    () =>
      story.scenes.map((s) => ({
        id: s.id,
        type: "scene",
        position: { x: s.position.x, y: s.position.y },
        data: { scene: s, isStart: s.id === story.start_scene, errors: errorsByScene.get(s.id) ?? 0, selected: s.id === selected, thumb: thumbOf(s) },
        deletable: false,
      })),
    [story.scenes, story.start_scene, errorsByScene, selected, slug],
  );
  const [nodes, setNodes] = useState<SceneNode[]>(built);
  useEffect(() => setNodes(built), [built]);

  const edges = useMemo<Edge[]>(
    () =>
      sceneLinks(story).map((l) => ({
        id: l.id,
        source: l.source,
        target: l.target,
        label: l.label || undefined,
        markerEnd: { type: MarkerType.ArrowClosed },
        className: l.source === selected || l.target === selected ? "hot" : undefined,
      })),
    [story, selected],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      colorMode="dark"
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.2}
      onNodesChange={(changes: NodeChange<SceneNode>[]) => setNodes((n) => applyNodeChanges(changes, n))}
      onNodeDragStop={(_e, node) =>
        update((d) => {
          const s = d.scenes.find((x) => x.id === node.id);
          if (s) s.position = { x: Math.round(node.position.x), y: Math.round(node.position.y) };
        })
      }
      onNodeClick={(_e, node) => onSelect(node.id)}
      onPaneClick={() => onSelect(null)}
      onConnect={(c) => c.source && c.target && update((d) => connect(d, c.source, c.target))}
      onEdgesDelete={(deleted) => update((d) => deleted.forEach((e) => unlink(d, e.id)))}
      onPaneContextMenu={(e) => {
        e.preventDefault();
        const p = flow.screenToFlowPosition({ x: e.clientX, y: e.clientY });
        addAt(p.x, p.y);
      }}
      deleteKeyCode={["Delete", "Backspace"]}
    >
      <Background gap={24} />
      <Controls showInteractive={false} />
      <div className="graph-toolbar">
        <button
          onClick={() => {
            const rect = document.querySelector(".graph")?.getBoundingClientRect();
            const p = flow.screenToFlowPosition({
              x: (rect?.left ?? 0) + (rect?.width ?? 600) / 2,
              y: (rect?.top ?? 0) + (rect?.height ?? 300) / 2,
            });
            addAt(p.x, p.y);
          }}
        >
          + Scene
        </button>
        <span className="muted hint">Drag from a scene's right dot to another scene to add a path · select a path and press Delete to remove it · right-click to add a scene there</span>
      </div>
    </ReactFlow>
  );
}

export function SceneGraph(props: { selected: string | null; onSelect: (id: string | null) => void }) {
  return (
    <div className="graph">
      <ReactFlowProvider>
        <Graph {...props} />
      </ReactFlowProvider>
    </div>
  );
}
