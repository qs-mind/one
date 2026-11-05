// Packages the core as an embedded Python in build/core/: the python-build-standalone runtime pinned in
// core/runtime.json, One's locked packages (core/runtime.lock, with hashes), the qsone package with its data
// (agent instructions, templates, typst files, open-licence fonts), trimmed and bytecode only, plus the third-party
// notices. Tauri ships build/core/ as the resource folder core/ (desktop/tauri.release.conf.json), and the shell starts
// core/bin/python3 (core\python.exe on Windows) with -I -m qsone. The Sandbox's CPython for WASI is not packaged: the
// core downloads it on first use into <data>/sandbox, as it does the search models.
//
//   node scripts/package-core.mjs [--target <triple>]     (default: this machine's)
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  createReadStream,
  createWriteStream,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
} from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { root } from "./python.mjs";

export const runtime = JSON.parse(readFileSync(path.join(root, "core", "runtime.json"), "utf8"));
const minor = runtime.python.split(".").slice(0, 2).join("."); // "3.12"

// The Sandbox's guest code is read as source and run by CPython for WASI, which cannot load this Python's bytecode.
const KEEP_SOURCE = [path.join("qsone", "sandbox", "guest")];

export function hostTarget() {
  const targets = {
    "linux-x64": "x86_64-unknown-linux-gnu",
    "win32-x64": "x86_64-pc-windows-msvc",
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x64": "x86_64-apple-darwin",
  };
  const target = targets[`${process.platform}-${process.arch}`];
  if (!target) throw new Error(`No runtime for ${process.platform}-${process.arch}`);
  return target;
}

/** Where things are inside an unpacked runtime: Windows keeps python.exe and Lib/ at the top. */
export function layout(dir, target) {
  const win = target.includes("windows");
  const lib = win ? path.join(dir, "Lib") : path.join(dir, "lib", `python${minor}`);
  return {
    win,
    python: win ? path.join(dir, "python.exe") : path.join(dir, "bin", "python3"),
    lib,
    site: path.join(lib, "site-packages"),
  };
}

export function sha256Of(file) {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    createReadStream(file)
      .on("error", reject)
      .on("data", (chunk) => hash.update(chunk))
      .on("end", () => resolve(hash.digest("hex")));
  });
}

/** Downloads `url` to `dest` unless a file with the right SHA-256 is already there. A file whose checksum differs
 * is deleted and the download refused. */
export async function download(url, sha256, dest) {
  if (existsSync(dest)) {
    if ((await sha256Of(dest)) === sha256) return dest;
    rmSync(dest);
  }
  mkdirSync(path.dirname(dest), { recursive: true });
  const part = `${dest}.part`;
  const response = await fetch(url);
  if (!response.ok || !response.body) throw new Error(`Download failed: ${url} answered ${response.status}`);
  await pipeline(Readable.fromWeb(response.body), createWriteStream(part));
  const got = await sha256Of(part);
  if (got !== sha256) {
    rmSync(part, { force: true });
    throw new Error(`Checksum differs for ${url}: expected ${sha256}, got ${got}. The file was deleted.`);
  }
  renameSync(part, dest);
  return dest;
}

function run(program, args, options = {}) {
  const result = spawnSync(program, args, { stdio: "inherit", ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${program} ${args.join(" ")} failed (exit ${result.status})`);
}

/** Unpacks the runtime archive (top folder `python/`) into `dir`. tar runs inside the staging folder with a
 * relative archive path, so Git for Windows' tar never reads `C:` as a host name. */
export function unpack(archive, dir) {
  const staging = `${dir}.part`;
  rmSync(staging, { recursive: true, force: true });
  mkdirSync(staging, { recursive: true });
  run("tar", ["-xzf", path.relative(staging, archive)], { cwd: staging });
  rmSync(dir, { recursive: true, force: true });
  renameSync(path.join(staging, "python"), dir);
  rmSync(staging, { recursive: true, force: true });
}

function walk(dir, visit) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (visit(full, entry) === false) continue; // removed: do not go inside
    if (entry.isDirectory()) walk(full, visit);
  }
}

const remove = (p) => rmSync(p, { recursive: true, force: true });
const each = (dir, test, act) => existsSync(dir) && readdirSync(dir).filter(test).forEach((n) => act(path.join(dir, n)));

/** Removes what must not ship (decision 3): pip, ensurepip, idlelib, tkinter and Tcl/Tk, the standard library's
 * tests and test modules, headers, every package's tests, static libraries and readline (GPL). Also every program
 * but Python itself (pip's and the packages' console scripts, which point at the build folder), and the symbolic
 * links, which the installers would copy twice: bin/python3 becomes the interpreter itself. */
export function trim(dir, target) {
  const { win, lib, site } = layout(dir, target);
  each(site, (n) => n === "pip" || /^pip-.*\.dist-info$/.test(n), remove);
  for (const name of ["ensurepip", "idlelib", "tkinter", "test"]) remove(path.join(lib, name));
  remove(path.join(dir, "include"));
  if (win) {
    remove(path.join(dir, "tcl"));
    remove(path.join(dir, "libs")); // import and static libraries
    remove(path.join(dir, "Scripts"));
    each(path.join(dir, "DLLs"), (n) => /^(_tkinter\.pyd|tcl\d+t?\.dll|tk\d+t?\.dll|_test\w*\.pyd|_ctypes_test\.pyd)$/.test(n), remove);
  } else {
    each(path.join(dir, "lib"), (n) => /^(itcl|tcl|tk|thread)\d|^libtcl|^libtk/.test(n), remove);
    each(path.join(lib, "lib-dynload"), (n) => /^(_tkinter|_test\w*|_ctypes_test|readline)\./.test(n), remove);
    const bin = path.join(dir, "bin");
    const real = path.join(bin, `python${minor}`);
    if (existsSync(real)) {
      each(bin, (n) => n !== `python${minor}`, remove);
      renameSync(real, path.join(bin, "python3"));
    }
  }
  walk(dir, (full, entry) => {
    if (entry.isSymbolicLink()) {
      remove(full); // only links to files beside them are left (libpython's development name)
      return false;
    }
    if (entry.isDirectory() && (entry.name === "__pycache__" || (entry.name === "tests" && full.startsWith(lib)))) {
      remove(full);
      return false;
    }
    if (entry.isFile() && /\.(a|lib)$/.test(entry.name)) remove(full);
    if (entry.isFile() && /^readline\.[\w.-]*(so|pyd|dylib)$/.test(entry.name)) remove(full);
  });
}

/** Copies the qsone package (code and data) into site-packages, without bytecode caches. */
export function copyCore(from, site) {
  const to = path.join(site, "qsone");
  remove(to);
  cpSync(from, to, { recursive: true, filter: (p) => path.basename(p) !== "__pycache__" && !p.endsWith(".pyc") });
  return to;
}

/** Thmanyah Sans is licensed for QS Mind's own use and never ships in this public app. */
export function refuseLicensedFonts(dir) {
  const found = [];
  walk(dir, (full) => {
    if (/thmanyah/i.test(path.basename(full))) found.push(full);
  });
  if (found.length) throw new Error(`Licensed font files must never ship: ${found.join(", ")}`);
}

/** Precompiles the library with `compileall -b` (a .pyc beside each module) and deletes every .py, ours included,
 * except KEEP_SOURCE. Tracebacks still name the file and line. */
export function bytecodeOnly(python, lib) {
  run(python, ["-I", "-m", "compileall", "-b", "-q", "-j0", lib]);
  const site = path.join(lib, "site-packages");
  const kept = KEEP_SOURCE.map((p) => path.join(site, p) + path.sep);
  walk(lib, (full, entry) => {
    if (entry.isDirectory() && entry.name === "__pycache__") {
      remove(full);
      return false;
    }
    if (entry.isFile() && entry.name.endsWith(".py") && !kept.some((k) => full.startsWith(k))) remove(full);
  });
}

export function sizeOf(dir) {
  let bytes = 0;
  let files = 0;
  walk(dir, (full, entry) => {
    if (entry.isFile()) {
      bytes += lstatSync(full).size;
      files += 1;
    }
  });
  return { bytes, files };
}

export async function packageCore({ target = hostTarget(), out = path.join(root, "build", "core") } = {}) {
  const pinned = runtime.targets[target];
  if (!pinned) throw new Error(`core/runtime.json has no target ${target}`);
  const archive = path.join(root, "build", "cache", path.basename(new URL(pinned.url).pathname));
  console.log(`runtime: ${path.basename(archive)}`);
  await download(pinned.url, pinned.sha256, archive);
  unpack(archive, out);
  const { python, lib, site } = layout(out, target);
  run("uv", [
    "pip", "install", "--python", python, "--require-hashes", "--no-deps", "--link-mode", "copy",
    "--quiet", "-r", path.join(root, "core", "runtime.lock"),
  ]);
  copyCore(path.join(root, "core", "qsone"), site);
  trim(out, target);
  refuseLicensedFonts(out);
  bytecodeOnly(python, lib);
  const { writeNotices } = await import("./notices.mjs"); // it imports this file
  await writeNotices({ python, out: path.join(out, "THIRD-PARTY-NOTICES.txt"), target });
  const { bytes, files } = sizeOf(out);
  console.log(`build/core: ${(bytes / 1e6).toFixed(1)} MB in ${files} files; start it with ${path.relative(root, python)}`);
  return python;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const at = process.argv.indexOf("--target");
  packageCore(at > 0 ? { target: process.argv[at + 1] } : {}).catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
