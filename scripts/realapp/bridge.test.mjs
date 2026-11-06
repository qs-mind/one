// The real-window bridge (ui/src/testbridge.ts) never ships: a production build, even one made with the bridge's
// variables set, has none of its code, and the dev hook in main.tsx stays behind import.meta.env.
import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterAll, expect, test } from "vitest";
import { root } from "../python.mjs";

const out = mkdtempSync(path.join(tmpdir(), "qsone-bridge-build-"));
afterAll(() => rmSync(out, { recursive: true, force: true }));

const files = (dir) => readdirSync(dir).flatMap((f) => (statSync(path.join(dir, f)).isDirectory() ? files(path.join(dir, f)) : [path.join(dir, f)]));

// words only the bridge has (its answers' errors and state), its module's name and its variables'
const BRIDGE = [/nothing matches /, /needs a query/, /rootFontSize/, /testbridge/, /VITE_QSONE_TEST_BRIDGE/];

/** `vite build` in its own process (vitest's NODE_ENV=test would make it a dev build), with the walk's variables set. */
function viteBuild(dir, mode) {
  const { NODE_ENV: _, ...env } = process.env;
  const vite = path.join(root, "node_modules", "vite", "bin", "vite.js");
  const result = spawnSync(process.execPath, [vite, "build", "--mode", mode, "--outDir", dir, "--emptyOutDir", "--logLevel", "error"], {
    cwd: root,
    env: { ...env, ...(mode === "development" ? { NODE_ENV: "development" } : {}), VITE_QSONE_TEST_BRIDGE: "1", VITE_QSONE_TEST_BRIDGE_URL: "ws://127.0.0.1:1/token" },
    encoding: "utf8",
  });
  expect(result.status, result.stderr).toBe(0);
  return files(dir)
    .filter((f) => /\.(js|html)$/.test(f))
    .map((f) => ({ file: path.relative(dir, f), text: readFileSync(f, "utf8") }));
}

test("a production build has no bridge code, even with the bridge's variables set", { timeout: 240_000 }, () => {
  const built = viteBuild(path.join(out, "production"), "production");
  expect(built.length).toBeGreaterThan(0);
  for (const { file, text } of built) for (const word of BRIDGE) expect(word.test(text), `${file} has ${word}`).toBe(false);
});

test("the words looked for find the bridge where it is built in (a development build)", { timeout: 240_000 }, () => {
  const all = viteBuild(path.join(out, "development"), "development")
    .map((f) => f.text)
    .join("\n");
  for (const word of BRIDGE.slice(0, 3)) expect(word.test(all), String(word)).toBe(true);
});

test("main.tsx loads the bridge only behind the dev server's variable", () => {
  const main = readFileSync(path.join(root, "ui/src/main.tsx"), "utf8");
  expect(main).toMatch(/if \(import\.meta\.env\.DEV && import\.meta\.env\.VITE_QSONE_TEST_BRIDGE === "1"\) \{\n[^}]*import\("\.\/testbridge"\)/);
  expect(main.match(/testbridge/g)).toHaveLength(1);
});
