// Every script or test that starts a core of its own keeps it off the engineer's system key store. On 5 Nov 2026 a smoke
// run of the packaged core (a fresh data folder, the real key store) wrote over the key of the engineer's own Engineer
// Records. A spawned core gets keyring's "fail" backend, so it keeps its keys in its own data folder; the core's tests
// in this process use the memory key store (core/tests/conftest.py).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "vitest";
import { ISOLATED_KEYS } from "./smoke-core.mjs";
import { root } from "./python.mjs";

const STARTS_CORE = /["']-m["']\s*,\s*["']qsone["']|-m qsone(?![\w.])/;
const ISOLATES = /ISOLATED_KEYS|PYTHON_KEYRING_BACKEND["']?\s*[:=,]\s*["']keyring\.backends\.fail\.Keyring/;
// Files that start a core with the key store they are given, on purpose, and why.
const ALLOWED = {
  "scripts/core-dev.ts":
    "the dev app's own core, with the engineer's data folder and key store; the bench passes `-m tests.bench`, which puts a key store in memory first",
  "scripts/fixtures/fake-core.mjs": "a stand-in for the core in core-dev.test.ts: it keeps no keys",
};
const SKIP = new Set(["node_modules", ".git", ".venv", "build", "dist", "target", "docs", ".claude"]);
const SELF = "scripts/keystore-isolation.test.mjs";

function sources(dir = root) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return SKIP.has(entry.name) ? [] : sources(full);
    return /\.(mjs|js|ts|tsx|py)$/.test(entry.name) ? [path.relative(root, full).split(path.sep).join("/")] : [];
  });
}

test("every script or test that starts a core keeps it off the system key store", () => {
  const starters = sources().filter((file) => file !== SELF && STARTS_CORE.test(readFileSync(path.join(root, file), "utf8")));
  expect(starters).toContain("scripts/smoke-core.mjs"); // the guard still finds what it guards
  const open = starters.filter((file) => !(file in ALLOWED) && !ISOLATES.test(readFileSync(path.join(root, file), "utf8")));
  expect(open, "set PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring (ISOLATED_KEYS in smoke-core.mjs)").toEqual([]);
});

test("the smoke test's core gets keyring's fail backend", () => {
  expect(ISOLATED_KEYS).toEqual({ PYTHON_KEYRING_BACKEND: "keyring.backends.fail.Keyring" });
  const smoke = readFileSync(path.join(root, "scripts/smoke-core.mjs"), "utf8");
  expect(smoke).toMatch(/\{ \.\.\.cleanEnv\(\), \.\.\.ISOLATED_KEYS,/); // after cleanEnv, which drops PYTHON*
});

test("the bench's core puts its key store in memory before the core starts", () => {
  const bench = readFileSync(path.join(root, "core/tests/bench/__main__.py"), "utf8");
  // guard.install(allow): `allow` names hosts the bench may reach; the key store goes in memory either way
  const install = bench.search(/^\s*guard\.install\([^)]*\)/m);
  expect(install).toBeGreaterThan(-1);
  expect(install).toBeLessThan(bench.indexOf("core_main("));
  const guard = readFileSync(path.join(root, "core/tests/bench/guard.py"), "utf8");
  const body = guard.slice(guard.indexOf("def install("), guard.indexOf("def ", guard.indexOf("def install(") + 1));
  expect(body).toMatch(/keyring\.set_keyring\(MemoryKeyring\(/);
  expect(readFileSync(path.join(root, "vite.bench.config.ts"), "utf8")).toMatch(/"-m", "tests\.bench"/);
});
