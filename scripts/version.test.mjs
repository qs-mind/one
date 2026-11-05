import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, test } from "vitest";
import { check, FILES, read, root, set } from "./version.mjs";

const made = [];
afterEach(() => made.splice(0).forEach((dir) => rmSync(dir, { recursive: true, force: true })));

/** A copy of every version file of this repository, to change freely. */
function copy() {
  const dir = mkdtempSync(path.join(tmpdir(), "qsone-version-"));
  made.push(dir);
  for (const file of Object.keys(FILES)) {
    mkdirSync(path.dirname(path.join(dir, file)), { recursive: true });
    cpSync(path.join(root, file), path.join(dir, file));
  }
  return dir;
}

test("this repository has one version everywhere", () => {
  const version = check();
  expect(read().map((f) => f.version)).toEqual(Object.keys(FILES).map(() => version));
});

test("versions must agree everywhere", () => {
  const dir = copy();
  const toml = path.join(dir, "core/pyproject.toml");
  writeFileSync(toml, readFileSync(toml, "utf8").replace(/^version = "[^"]*"/m, 'version = "0.0.9"'));
  expect(() => check(undefined, dir)).toThrow(/core\/pyproject\.toml: 0\.0\.9/);
  expect(() => check("0.0.9", dir)).toThrow(/package\.json: .*\n.*package-lock\.json/);
  const lock = path.join(dir, "package-lock.json");
  const p = JSON.parse(readFileSync(lock, "utf8"));
  p.packages[""].version = "0.0.8"; // the lock's two places disagree
  writeFileSync(lock, JSON.stringify(p, null, 2) + "\n");
  expect(() => check(undefined, dir)).toThrow(/package-lock\.json: \S+ \/ 0\.0\.8/);
});

test("set writes every file and check passes", () => {
  const dir = copy();
  const before = Object.fromEntries(Object.keys(FILES).map((f) => [f, readFileSync(path.join(dir, f), "utf8")]));
  expect(set("0.1.1", dir)).toBe("0.1.1");
  expect(check("0.1.1", dir)).toBe("0.1.1");
  for (const file of Object.keys(FILES)) {
    const after = readFileSync(path.join(dir, file), "utf8");
    // only the version changed: every other line is as it was
    const changed = after.split("\n").filter((l, i) => l !== before[file].split("\n")[i]);
    expect(changed.length, file).toBeGreaterThan(0);
    expect(changed.every((l) => l.includes("0.1.1")), file).toBe(true);
  }
  // Cargo.lock: the app's own entry only, never a crate that happens to share the old version
  const cargoLock = readFileSync(path.join(dir, "desktop/Cargo.lock"), "utf8");
  expect(cargoLock).toMatch(/name = "qs-mind-one"\nversion = "0\.1\.1"/);
  const count = (text) => text.split("\n").filter((l) => l === 'version = "0.1.1"').length;
  expect(count(cargoLock)).toBe(count(before["desktop/Cargo.lock"]) + 1);
});

test("set refuses what is not a version", () => {
  const dir = copy();
  for (const bad of [undefined, "", "1.2", "v1.2.3", "1.2.3; rm -rf /", "1.2.3\n"]) {
    expect(() => set(bad, dir)).toThrow(/Not a version/);
  }
  expect(set("1.0.0-rc.1", dir)).toBe("1.0.0-rc.1");
});
