import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, type AssetInfo, type Issue, type Story } from "../api";

export type SaveState = "saved" | "unsaved" | "saving" | "error";

export interface StoryEditor {
  slug: string;
  story: Story;
  issues: Issue[];
  assets: AssetInfo[];
  saveState: SaveState;
  saveError: string | null;
  /** Apply a mutation to a copy of the story; it autosaves shortly after. */
  update: (mutate: (draft: Story) => void) => void;
  refreshAssets: () => Promise<void>;
  saveNow: () => Promise<void>;
}

const AUTOSAVE_MS = 700;

export function useStoryEditor(slug: string) {
  const [story, setStory] = useState<Story | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [assets, setAssets] = useState<AssetInfo[]>([]);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const latest = useRef<Story | null>(null);
  const dirty = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const inFlight = useRef<Promise<void> | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([api.project(slug), api.assets(slug)])
      .then(([p, a]) => {
        if (!live) return;
        latest.current = p.story;
        setStory(p.story);
        setIssues(p.issues);
        setAssets(a);
      })
      .catch((e: Error) => live && setLoadError(e.message));
    return () => {
      live = false;
    };
  }, [slug]);

  const saveNow = useCallback(async () => {
    window.clearTimeout(timer.current);
    if (inFlight.current) await inFlight.current;
    if (!dirty.current || !latest.current) return;
    dirty.current = false;
    const snapshot = latest.current;
    setSaveState("saving");
    inFlight.current = api
      .saveProject(slug, snapshot)
      .then((r) => {
        setIssues(r.issues);
        setSaveError(null);
        setSaveState(dirty.current ? "unsaved" : "saved");
      })
      .catch((e: Error) => {
        dirty.current = true;
        setSaveError(e.message);
        setSaveState("error");
      })
      .finally(() => {
        inFlight.current = null;
      });
    await inFlight.current;
  }, [slug]);

  const update = useCallback(
    (mutate: (draft: Story) => void) => {
      setStory((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev);
        mutate(next);
        latest.current = next;
        return next;
      });
      dirty.current = true;
      setSaveState("unsaved");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void saveNow(), AUTOSAVE_MS);
    },
    [saveNow],
  );

  // Save on leaving the editor or closing the tab.
  useEffect(() => {
    const onUnload = (e: BeforeUnloadEvent) => {
      if (dirty.current) {
        void saveNow();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      void saveNow();
    };
  }, [saveNow]);

  const refreshAssets = useCallback(async () => setAssets(await api.assets(slug)), [slug]);

  const editor: StoryEditor | null = story
    ? { slug, story, issues, assets, saveState, saveError, update, refreshAssets, saveNow }
    : null;
  return { editor, loadError };
}

export const EditorContext = createContext<StoryEditor | null>(null);

export function useEditor(): StoryEditor {
  const ctx = useContext(EditorContext);
  if (!ctx) throw new Error("useEditor outside EditorContext");
  return ctx;
}
