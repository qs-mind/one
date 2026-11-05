// Writes THIRD-PARTY-NOTICES.txt for the installed app: the embedded Python and every Python package in it, the
// open-licence fonts the exports use, the screen's production npm packages and the shell's Rust crates, each with its
// licence and licence files. The licence gate (decision 22) refuses GPL, LGPL, AGPL and SSPL, and a package whose
// licence cannot be found, unless the package is in ALLOW with the reason it is acceptable.
//
//   node scripts/notices.mjs [--python <python>] [--out <file>] [--target <triple>]
//   (defaults: the packaged core's Python, build/core/THIRD-PARTY-NOTICES.txt, this machine)
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { hostTarget, layout } from "./package-core.mjs";
import { root } from "./python.mjs";

/** Packages the gate lets through although their licence alone would stop them: name → why. */
export const ALLOW = {
  "@platejs/diff": "no licence field; its LICENSE file gives Apache-2.0 (as slate-diff) and MIT",
};

const COPYLEFT = /\b(A?GPL|LGPL|SSPL)\b|GNU (General|Lesser|Library|Affero)|Server Side Public/i;
const LICENCE_FILE = /^(licen[cs]e|copying|notice|copyright)/i;

/** The licence of a package as one expression: Python metadata (License-Expression, else a short License field,
 * else its licence classifiers, all of which must hold), npm's `license` (or the old `licenses` list) and Cargo's
 * `license` (where "/" is the old spelling of OR). */
export function licenceOf(pkg) {
  if (pkg.license_expression) return pkg.license_expression.trim();
  const npm = pkg.licenses ?? (typeof pkg.license === "object" && pkg.license ? [pkg.license] : null);
  if (Array.isArray(npm)) return npm.map((l) => (typeof l === "string" ? l : l.type)).join(" OR ");
  const text = typeof pkg.license === "string" ? pkg.license.trim() : "";
  if (text && !text.includes("\n") && text.length <= 100 && text.toUpperCase() !== "UNKNOWN") {
    return pkg.cargo ? text.replace(/\s*\/\s*/g, " OR ") : text;
  }
  const classifiers = (pkg.classifiers ?? [])
    .filter((c) => c.startsWith("License ::"))
    .map((c) => c.split("::").pop().trim());
  return classifiers.join(" AND ");
}

/** True when the expression allows use without copyleft: an OR needs one acceptable side, an AND needs both.
 * Free text (a classifier such as "GNU Library or Lesser General Public License") is read as one term. */
export function permissive(expression) {
  const tokens = expression.match(/\(|\)|[^\s()]+/g) ?? [];
  let at = 0;
  const term = () => {
    if (tokens[at] === "(") {
      at += 1;
      const value = or();
      at += 1; // ")"
      return value;
    }
    const words = [];
    while (at < tokens.length && !["AND", "OR", ")"].includes(tokens[at])) words.push(tokens[at++]);
    const text = words.join(" ");
    return text !== "" && !COPYLEFT.test(text);
  };
  const and = () => {
    let value = term();
    while (tokens[at] === "AND") {
      at += 1;
      value = term() && value;
    }
    return value;
  };
  const or = () => {
    let value = and();
    while (tokens[at] === "OR") {
      at += 1;
      value = and() || value;
    }
    return value;
  };
  return tokens.length > 0 && or();
}

/** Throws, naming every package whose licence is copyleft or missing and that ALLOW does not list with a reason.
 * Returns the list, each allowed package marked with its reason. */
export function gate(list, allow = ALLOW) {
  const refused = [];
  const checked = list.map((pkg) => {
    if (permissive(pkg.licence ?? "")) return pkg;
    const reason = allow[pkg.name];
    if (typeof reason === "string" && reason.trim()) return { ...pkg, allowed: reason };
    refused.push(`${pkg.name} (${pkg.licence || "no licence found"})`);
    return pkg;
  });
  if (refused.length) throw new Error(`The licence gate refuses: ${refused.join(", ")}`);
  return checked;
}

function licenceFiles(dir) {
  if (!dir || !existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile() && LICENCE_FILE.test(e.name))
    .map((e) => ({ name: e.name, text: readFileSync(path.join(dir, e.name), "utf8") }));
}

// Run by the packaged Python: every installed distribution with its metadata and the licence files in its
// dist-info, plus the versions of the libraries python-build-standalone links in.
const PYTHON_LIST = String.raw`
import json, sqlite3, ssl, sys, zlib, pyexpat
from importlib import metadata
out = []
for d in metadata.distributions():
    m = d.metadata
    files = []
    for f in d.files or []:
        s = str(f).replace("\\", "/")
        if ".dist-info/" in s and ("/licenses/" in s or s.rsplit("/", 1)[-1].upper().startswith(("LICEN", "COPYING", "NOTICE"))):
            try:
                files.append({"name": s.rsplit("/", 1)[-1], "text": f.read_text(encoding="utf-8")})
            except (OSError, UnicodeDecodeError):
                pass
    out.append({"name": m["Name"], "version": m["Version"], "license_expression": m.get("License-Expression"),
                "license": m.get("License"), "classifiers": m.get_all("Classifier") or [], "files": files})
runtime = {"python": sys.version.split()[0], "openssl": ssl.OPENSSL_VERSION, "sqlite": sqlite3.sqlite_version,
           "zlib": zlib.ZLIB_RUNTIME_VERSION, "expat": pyexpat.EXPAT_VERSION}
print(json.dumps({"packages": sorted(out, key=lambda p: p["name"].lower()), "runtime": runtime}))
`;

export function pythonPackages(python) {
  const result = spawnSync(python, ["-I", "-c", PYTHON_LIST], { encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
  if (result.status !== 0) throw new Error(`Could not list the Python packages: ${result.stderr}`);
  const { packages, runtime } = JSON.parse(result.stdout);
  return {
    runtime,
    packages: packages.map((p) => ({ name: p.name, version: p.version, licence: licenceOf(p), files: p.files })),
  };
}

/** The production npm packages, from package-lock.json, with the licence files of those installed here. */
export function npmPackages(lockFile = path.join(root, "package-lock.json")) {
  const lock = JSON.parse(readFileSync(lockFile, "utf8"));
  return Object.entries(lock.packages)
    .filter(([where, p]) => where.startsWith("node_modules/") && !p.dev && !p.devOptional)
    .map(([where, p]) => {
      const name = where.slice(where.lastIndexOf("node_modules/") + "node_modules/".length);
      const dir = path.join(path.dirname(lockFile), where);
      return { name, version: p.version, licence: licenceOf(p), files: licenceFiles(dir) };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** The shell's Rust crates for this target, from `cargo metadata`, without One's own crate. */
export function cargoPackages(target, manifest = path.join(root, "desktop", "Cargo.toml")) {
  const args = ["metadata", "--format-version", "1", "--locked", "--manifest-path", manifest, "--filter-platform", target];
  const result = spawnSync("cargo", args, { encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
  if (result.error) throw new Error(`cargo is needed for the Rust crates' notices: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`cargo metadata failed: ${result.stderr}`);
  const { packages, workspace_members: ours } = JSON.parse(result.stdout);
  return packages
    .filter((p) => !ours.includes(p.id))
    .map((p) => ({
      name: p.name,
      version: p.version,
      licence: licenceOf({ license: p.license ?? "", cargo: true }),
      files: licenceFiles(path.dirname(p.manifest_path)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version));
}

function section(title, packages) {
  const lines = [`${"=".repeat(78)}\n${title} (${packages.length})\n${"=".repeat(78)}\n`];
  for (const p of packages) {
    lines.push(`\n--- ${p.name} ${p.version}: ${p.licence}${p.allowed ? ` (allowed: ${p.allowed})` : ""}\n`);
    for (const f of p.files) lines.push(`\n[${f.name}]\n${f.text.trim()}\n`);
  }
  return lines.join("");
}

export function notices({ python, target }) {
  const { runtime, packages } = pythonPackages(python);
  const lib = target.includes("windows") ? path.dirname(python) : path.join(path.dirname(python), "..", "lib", `python${runtime.python.split(".").slice(0, 2).join(".")}`);
  const cpython = {
    name: "CPython",
    version: runtime.python,
    licence: "PSF-2.0",
    files: licenceFiles(lib).filter((f) => f.name === "LICENSE.txt"),
  };
  const ofl = path.join(root, "core", "qsone", "fonts", "OFL.txt");
  const fonts = { name: "Kumbh Sans, Zain", version: "", licence: "OFL-1.1", files: [{ name: "OFL.txt", text: readFileSync(ofl, "utf8") }] };
  const linked =
    `CPython ${runtime.python} is python-build-standalone's build (github.com/astral-sh/python-build-standalone). ` +
    `It links in, among others: ${runtime.openssl} (Apache-2.0), SQLite ${runtime.sqlite} (public domain), ` +
    `zlib ${runtime.zlib} (Zlib) and ${runtime.expat} (MIT); that project's full release archives carry each licence.`;
  return [
    "QS Mind One: third-party notices\n",
    "One itself is under the FSL-1.1-ALv2 licence (LICENSE.md). It ships the software below, each under its own licence.\n\n",
    section("Python runtime", gate([cpython])),
    `\n${linked}\n\n`,
    section("Python packages", gate(packages)),
    "\n",
    section("Fonts used by the exports", gate([fonts])),
    "\n",
    section("Screen (npm packages)", gate(npmPackages())),
    "\n",
    section("Shell (Rust crates)", gate(cargoPackages(target))),
  ].join("");
}

export async function writeNotices({ python, out, target }) {
  mkdirSync(path.dirname(out), { recursive: true });
  writeFileSync(out, notices({ python, target }), "utf8");
  return out;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const arg = (name) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined);
  const target = arg("--target") ?? hostTarget();
  const python = arg("--python") ?? layout(path.join(root, "build", "core"), target).python;
  const out = arg("--out") ?? path.join(root, "build", "core", "THIRD-PARTY-NOTICES.txt");
  try {
    await writeNotices({ python, out, target });
    console.log(`notices: ${path.relative(root, out)}`);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}
