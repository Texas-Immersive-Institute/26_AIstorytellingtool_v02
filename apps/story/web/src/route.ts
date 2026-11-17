import { useEffect, useState } from "react";

/**
 * Hash routes:
 *   #/                       stories
 *   #/settings               AI, matching, LAN and folder settings
 *   #/project/<slug>         editor
 *   #/project/<slug>/run     Debug view (operator)
 *   #/stage                  Stage view (the big screen)
 *   #/chat                   Chat view (audience devices)
 */
export type Route =
  | { name: "projects" }
  | { name: "settings" }
  | { name: "project"; slug: string }
  | { name: "run"; slug: string }
  | { name: "stage" }
  | { name: "chat" };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "project" && parts[1]) {
    return parts[2] === "run" ? { name: "run", slug: parts[1] } : { name: "project", slug: parts[1] };
  }
  if (parts[0] === "chat") return { name: "chat" };
  if (parts[0] === "stage") return { name: "stage" };
  if (parts[0] === "settings") return { name: "settings" };
  return { name: "projects" };
}

export function href(route: Route): string {
  switch (route.name) {
    case "project":
      return `#/project/${encodeURIComponent(route.slug)}`;
    case "run":
      return `#/project/${encodeURIComponent(route.slug)}/run`;
    case "chat":
    case "stage":
    case "settings":
      return `#/${route.name}`;
    default:
      return "#/";
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export const go = (route: Route) => {
  window.location.hash = href(route);
};
