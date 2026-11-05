// One version everywhere (decision 21): package.json and package-lock.json, desktop/Cargo.toml and Cargo.lock, the
// window's desktop/tauri.conf.json, core/pyproject.toml and qsone.__version__.
//
//   node scripts/version.mjs set <version>     writes it into every file
//   node scripts/version.mjs check [<version>] fails, naming every file that differs (no version: they must agree)
//   npm version <version>                      the same as set (this is package.json's "version" script)
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** A release version: 1.2.3, or 1.2.3-rc.1. */
export const VERSION = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;

const json = (read, write) => ({ read: (text) => read(JSON.parse(text)), write: (text, v) => write(JSON.parse(text), v) });
const toJson = (value) => JSON.stringify(value, null, 2) + "\n";

/** A line `<prefix>"<version>"` in a text file: the first one, or the first one after `after`. */
function line(prefix, after) {
  const find = (text) => {
    const start = after ? text.indexOf(after) : 0;
    if (start < 0) return undefined;
    const pattern = new RegExp(`^${prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"([^"]*)"`, "m");
    const found = pattern.exec(text.slice(start));
    return found && { at: start + found.index, length: found[0].length, version: found[1] };
  };
  return {
    read: (text) => find(text)?.version,
    write: (text, v) => {
      const found = find(text);
      if (!found) throw new Error("no version line");
      return text.slice(0, found.at) + `${prefix}"${v}"` + text.slice(found.at + found.length);
    },
  };
}

/** Every file that carries One's version, and how to read and write it there. */
export const FILES = {
  "package.json": json(
    (p) => p.version,
    (p, v) => toJson({ ...p, version: v }),
  ),
  "package-lock.json": json(
    (p) => (p.version === p.packages?.[""]?.version ? p.version : `${p.version} / ${p.packages?.[""]?.version}`),
    (p, v) => {
      p.version = v;
      p.packages[""].version = v;
      return toJson(p);
    },
  ),
  "desktop/Cargo.toml": line("version = ", "[package]"),
  "desktop/Cargo.lock": line("version = ", '\nname = "qs-mind-one"\n'),
  "desktop/tauri.conf.json": json(
    (c) => c.version,
    (c, v) => toJson({ ...c, version: v }),
  ),
  "core/pyproject.toml": line("version = ", "[project]"),
  "core/qsone/__init__.py": line("__version__ = "),
};

/** The version each file carries (undefined when it carries none). */
export function read(base = root) {
  return Object.entries(FILES).map(([file, way]) => {
    let version;
    try {
      version = way.read(readFileSync(path.join(base, file), "utf8"));
    } catch {
      version = undefined;
    }
    return { file, version };
  });
}

/** Throws, naming every file whose version is not `version` (default: the one package.json has). */
export function check(version, base = root) {
  const found = read(base);
  const want = version ?? found[0].version;
  const wrong = found.filter((f) => f.version !== want);
  if (wrong.length) {
    const list = wrong.map((f) => `  ${f.file}: ${f.version ?? "no version found"}`).join("\n");
    throw new Error(`These files are not at version ${want}:\n${list}\nRun: node scripts/version.mjs set ${want}`);
  }
  return want;
}

/** Writes `version` into every file. */
export function set(version, base = root) {
  if (!VERSION.test(version ?? "")) throw new Error(`Not a version: ${version} (use 1.2.3 or 1.2.3-rc.1)`);
  for (const [file, way] of Object.entries(FILES)) {
    const full = path.join(base, file);
    writeFileSync(full, way.write(readFileSync(full, "utf8"), version));
  }
  return check(version, base);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [command, version] = process.argv.slice(2);
  try {
    // `npm version <v>` has just written package.json and its lock, then runs this as its "version" script
    if (command === undefined && process.env.npm_lifecycle_event === "version") {
      console.log(`Every file is now at ${set(read()[0].version)}.`);
    } else if (command === "set") console.log(`Every file is now at ${set(version)}.`);
    else if (command === "check" || command === undefined) console.log(`Every file is at ${check(version)}.`);
    else throw new Error("Use: node scripts/version.mjs set <version> | check [<version>]");
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}
