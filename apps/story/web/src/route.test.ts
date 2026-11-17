import { href, parseRoute } from "./route";

test("parses hash routes", () => {
  expect(parseRoute("")).toEqual({ name: "projects" });
  expect(parseRoute("#/")).toEqual({ name: "projects" });
  expect(parseRoute("#/project/the-lighthouse-keeper")).toEqual({ name: "project", slug: "the-lighthouse-keeper" });
  expect(parseRoute("#/project/x/run")).toEqual({ name: "run", slug: "x" });
  expect(parseRoute("#/chat")).toEqual({ name: "chat" });
  expect(parseRoute("#/stage")).toEqual({ name: "stage" });
  expect(parseRoute("#/settings")).toEqual({ name: "settings" });
  expect(parseRoute("#/unknown")).toEqual({ name: "projects" });
});

test("href round-trips", () => {
  const route = { name: "project" as const, slug: "a story" };
  expect(parseRoute(href(route))).toEqual(route);
});
