import { useRef, useState } from "react";
import { exportUrl } from "../api";
import { href } from "../route";
import { Splitter, usePaneSize } from "../Splitter";
import { AssetsPanel, CharactersPanel, MemoryPanel, StoryPanel, VariablesPanel } from "./panels";
import { SceneEditor } from "./SceneEditor";
import { SceneGraph } from "./SceneGraph";
import { EditorContext, useStoryEditor, type StoryEditor } from "./useStoryEditor";

const TABS = ["Story", "Characters", "Variables", "Memory", "Assets"] as const;
type Tab = (typeof TABS)[number];

export function Editor({ slug }: { slug: string }) {
  const { editor, loadError } = useStoryEditor(slug);
  if (loadError)
    return (
      <div className="page">
        <a href="#/">← Stories</a>
        <p className="error">{loadError}</p>
      </div>
    );
  if (!editor) return <div className="centered">Loading…</div>;
  return (
    <EditorContext.Provider value={editor}>
      <EditorLayout editor={editor} />
    </EditorContext.Provider>
  );
}

function EditorLayout({ editor }: { editor: StoryEditor }) {
  const { story, issues, slug, saveState, saveError } = editor;
  const [tab, setTab] = useState<Tab>("Story");
  const [selected, setSelected] = useState<string | null>(story.start_scene);
  const [showIssues, setShowIssues] = useState(false);
  const [sidebarWidth, setSidebarWidth, resetSidebar] = usePaneSize("sidebar", 320, 200, 720);
  // the scene graph's share of the workspace height, in percent
  const [graphShare, setGraphShare, resetGraph] = usePaneSize("graph", 38, 10, 88);
  const workspace = useRef<HTMLElement>(null);
  const errors = issues.filter((i) => i.level === "error").length;

  return (
    <div className="editor" style={{ gridTemplateColumns: `${sidebarWidth}px 0 1fr` }}>
      <header className="editor-top">
        <a href="#/" onClick={() => void editor.saveNow()}>
          ← Stories
        </a>
        <h1>{story.title || "Untitled story"}</h1>
        <span className={`save ${saveState}`} title={saveError ?? ""}>
          {saveState === "saved" ? "Saved" : saveState === "saving" ? "Saving…" : saveState === "unsaved" ? "Unsaved" : "Save failed"}
        </span>
        <button className={errors ? "issues-btn error" : "issues-btn"} onClick={() => setShowIssues(!showIssues)}>
          {issues.length === 0 ? "✓ No issues" : `${errors} error${errors === 1 ? "" : "s"}, ${issues.length - errors} warning${issues.length - errors === 1 ? "" : "s"}`}
        </button>
        <a className="button" href={exportUrl(slug)} download onClick={() => void editor.saveNow()}>
          Export .zip
        </a>
        <a className="button primary" href={href({ name: "run", slug })} onClick={() => void editor.saveNow()}>
          ▶ Run
        </a>
        {showIssues && (
          <div className="issues-pop card">
            {issues.length === 0 && <span className="muted">Nothing to fix.</span>}
            <ul className="issues">
              {issues.map((i, n) => {
                const sceneId = i.where.match(/^scenes\/([^/]+)/)?.[1];
                return (
                  <li
                    key={n}
                    className={`${i.level}${sceneId ? " clickable" : ""}`}
                    onClick={() => {
                      if (sceneId) {
                        setSelected(sceneId);
                        setShowIssues(false);
                      }
                    }}
                  >
                    {sceneId && <strong>{story.scenes.find((s) => s.id === sceneId)?.title ?? sceneId}: </strong>}
                    {i.message} <code className="muted">{i.where}</code>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </header>

      <aside className="sidebar">
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        {tab === "Story" && <StoryPanel />}
        {tab === "Characters" && <CharactersPanel />}
        {tab === "Variables" && <VariablesPanel />}
        {tab === "Memory" && <MemoryPanel />}
        {tab === "Assets" && <AssetsPanel />}
      </aside>
      <Splitter axis="x" onDrag={(x) => setSidebarWidth(x)} onReset={resetSidebar} />

      <main className="workspace" ref={workspace} style={{ gridTemplateRows: `minmax(120px, ${graphShare}%) 0 1fr` }}>
        <SceneGraph selected={selected} onSelect={setSelected} />
        <Splitter
          axis="y"
          onDrag={(y) => {
            const r = workspace.current!.getBoundingClientRect();
            setGraphShare(((y - r.top) / r.height) * 100);
          }}
          onReset={resetGraph}
        />
        {selected ? (
          <SceneEditor sceneId={selected} onDeleted={() => setSelected(null)} />
        ) : (
          <div className="scene-editor empty muted">Select a scene on the graph to edit its beats.</div>
        )}
      </main>
    </div>
  );
}
