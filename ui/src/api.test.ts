import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("api()", () => {
  it("reaches the core through /api in development", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    await api("/health");
    expect(fetch).toHaveBeenCalledWith("/api/health", undefined);
  });

  it("passes the request on as it is", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    const init = { method: "POST", body: "{}" };
    await api("/projects/p1/files?name=%D8%B9", init);
    expect(fetch).toHaveBeenCalledWith("/api/projects/p1/files?name=%D8%B9", init);
  });
});

// Every screen calls api(), never fetch, so the installed app can carry every call (Plan 8 Task 2).
describe("no screen calls fetch itself", () => {
  const root = join(__dirname);
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? files(path) : [path];
    });

  it("only api.ts calls fetch", () => {
    const callers = files(root)
      .filter((path) => /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path))
      .map((path) => relative(root, path).replaceAll("\\", "/"))
      .filter((path) => !["api.ts", "test-setup.ts", "shell/testing.tsx"].includes(path) && !path.endsWith("fixtures.ts"))
      .filter((path) => /\bfetch\(|["'`]\/api[/"'`?]/.test(readFileSync(join(root, path), "utf8")));
    expect(callers).toEqual([]);
  });
});
