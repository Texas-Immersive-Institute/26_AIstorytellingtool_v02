import { useEffect, useState } from "react";
import { api, type SettingsOut } from "./api";
import { Chat } from "./chat/Chat";
import { Editor } from "./editor/Editor";
import { useRoute } from "./route";
import { Runner } from "./run/Runner";
import { StageView } from "./run/StageView";
import { Projects } from "./screens/Projects";
import { Settings } from "./screens/Settings";
import { Setup } from "./screens/Setup";

export default function App() {
  const route = useRoute();
  const [isHost, setIsHost] = useState<boolean | null>(null);
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .whoami()
      .then(async (who) => {
        setIsHost(who.is_host);
        if (who.is_host) setSettings(await api.settings());
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <Centered>Cannot reach the Story server: {error}</Centered>;
  if (isHost === null) return <Centered>Loading…</Centered>;
  // Audience devices only ever get the chat (Stage, Debug and authoring are host-only).
  if (!isHost || route.name === "chat") return <Chat />;
  if (route.name === "stage") return <StageView />;
  if (!settings) return <Centered>Loading…</Centered>;
  const changeFolder = () => setSettings({ ...settings, projects_dir: null });
  if (!settings.projects_dir) return <Setup settings={settings} onSaved={setSettings} />;
  if (route.name === "settings") return <Settings settings={settings} onChangeFolder={changeFolder} />;
  if (route.name === "project") return <Editor key={route.slug} slug={route.slug} />;
  if (route.name === "run") return <Runner key={route.slug} slug={route.slug} />;
  return <Projects settings={settings} onChangeFolder={changeFolder} />;
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="centered">{children}</div>;
}
