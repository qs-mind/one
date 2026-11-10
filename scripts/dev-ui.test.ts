// @vitest-environment node
// `vite --mode ui` (npm run dev:ui) serves the new interface without the core; every other serve mode starts it.
import { readFileSync } from "node:fs";
import type { ConfigEnv, PluginOption, UserConfig } from "vite";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import config from "../vite.config.ts";

const resolve = config as unknown as (env: ConfigEnv) => UserConfig;

function pluginNames(env: Partial<ConfigEnv>): string[] {
  const { plugins = [] } = resolve({ command: "serve", mode: "development", isSsrBuild: false, isPreview: false, ...env });
  const flat = (list: PluginOption[]): PluginOption[] => list.flatMap((p) => (Array.isArray(p) ? flat(p) : [p]));
  return flat(plugins).flatMap((p) => (p && typeof p === "object" && "name" in p ? [p.name] : []));
}

describe("the dev config", () => {
  let vitest: string | undefined;
  beforeEach(() => {
    vitest = process.env.VITEST;
    delete process.env.VITEST; // the config leaves the core out under Vitest; the test reads it as `vite` would
  });
  afterEach(() => {
    if (vitest !== undefined) process.env.VITEST = vitest;
  });

  it("drops the core in mode ui", () => {
    expect(pluginNames({ mode: "ui" })).not.toContain("qsone-core-dev");
  });

  it.each(["development", "production", "test"])("starts the core when serving in mode %s", (mode) => {
    expect(pluginNames({ mode })).toContain("qsone-core-dev");
  });

  it("never starts the core for a build", () => {
    expect(pluginNames({ command: "build", mode: "production" })).not.toContain("qsone-core-dev");
  });

  it("builds index.html alone: no rollupOptions.input", () => {
    const { build } = resolve({ command: "build", mode: "production", isSsrBuild: false, isPreview: false });
    expect(build?.rollupOptions?.input).toBeUndefined();
    expect(readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8")).not.toMatch(/\binput\s*:/);
  });
});
