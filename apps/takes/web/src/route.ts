import { useEffect, useState } from "react";

/**
 * Hash routes:
 *   #/                        projects
 *   #/settings                projects folder and ComfyUI address
 *   #/project/<slug>          a project's shots (the sequence)
 *   #/project/<slug>/<shot>   the same, with that shot open
 */
export type Route =
  | { name: "projects" }
  | { name: "settings" }
  | { name: "project"; slug: string; shot: string | null };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "project" && parts[1]) return { name: "project", slug: parts[1], shot: parts[2] ?? null };
  if (parts[0] === "settings") return { name: "settings" };
  return { name: "projects" };
}

export function href(route: Route): string {
  switch (route.name) {
    case "project":
      return `#/project/${encodeURIComponent(route.slug)}` + (route.shot ? `/${encodeURIComponent(route.shot)}` : "");
    case "settings":
      return "#/settings";
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

/** Go to a route; `replace` swaps the current history entry instead of adding one. */
export const go = (route: Route, replace = false) => {
  if (replace) window.location.replace(href(route));
  else window.location.hash = href(route);
};
