import { useEffect, useState } from "react";
import { api, type SettingsOut } from "./api";
import { ProjectScreen } from "./project/ProjectScreen";
import { useRoute } from "./route";
import { Projects } from "./screens/Projects";
import { Settings } from "./screens/Settings";
import { Setup } from "./screens/Setup";

export default function App() {
  const route = useRoute();
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .settings()
      .then(setSettings)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <div className="centered">Cannot reach the Takes server: {error}</div>;
  if (!settings) return <div className="centered">Loading…</div>;
  if (!settings.projects_dir) return <Setup settings={settings} onSaved={setSettings} />;
  if (route.name === "settings") return <Settings settings={settings} onSaved={setSettings} />;
  if (route.name === "project") return <ProjectScreen key={route.slug} slug={route.slug} shotId={route.shot} />;
  return <Projects settings={settings} />;
}
