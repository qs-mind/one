import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, test } from "vitest";
import { bytecodeOnly, copyCore, download, layout, refuseLicensedFonts, runtime, trim } from "./package-core.mjs";
import { corePython, root } from "./python.mjs";
import { cleanEnv } from "./smoke-core.mjs";

const dirs = [];
function tmp() {
  const dir = mkdtempSync(path.join(tmpdir(), "qsone-package-"));
  dirs.push(dir);
  return dir;
}
afterEach(() => dirs.splice(0).forEach((d) => rmSync(d, { recursive: true, force: true })));

function put(dir, files) {
  for (const name of files) {
    const file = path.join(dir, name);
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, name.endsWith(".py") ? "VALUE = 7\n" : "x");
  }
}

function serve(body) {
  return new Promise((resolve) => {
    const server = createServer((_req, res) => res.end(body));
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

test("a download whose checksum differs is refused and deleted", async () => {
  const body = Buffer.from("not the runtime");
  const server = await serve(body);
  try {
    const url = `http://127.0.0.1:${server.address().port}/python.tar.gz`;
    const dest = path.join(tmp(), "cache", "python.tar.gz");
    await expect(download(url, "0".repeat(64), dest)).rejects.toThrow(/Checksum differs/);
    expect(existsSync(dest)).toBe(false);
    expect(existsSync(`${dest}.part`)).toBe(false);

    const right = createHash("sha256").update(body).digest("hex");
    await download(url, right, dest);
    expect(readFileSync(dest)).toEqual(body);
  } finally {
    server.close();
  }
});

test("trim removes what must not ship and keeps what must", () => {
  const dir = tmp();
  const lib = "lib/python3.12";
  put(dir, [
    `${lib}/os.py`,
    `${lib}/tkinter/__init__.py`,
    `${lib}/test/test_x.py`,
    `${lib}/idlelib/idle.py`,
    `${lib}/ensurepip/__init__.py`,
    `${lib}/lib-dynload/readline.cpython-312-x86_64-linux-gnu.so`,
    `${lib}/lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so`,
    `${lib}/lib-dynload/_ssl.cpython-312-x86_64-linux-gnu.so`,
    `${lib}/site-packages/pip/__init__.py`,
    `${lib}/site-packages/pip-26.2.2.dist-info/METADATA`,
    `${lib}/site-packages/x/tests/test_x.py`,
    `${lib}/site-packages/x/__pycache__/mod.cpython-312.pyc`,
    `${lib}/site-packages/x/libstatic.a`,
    `${lib}/site-packages/x/mod.py`,
    `${lib}/site-packages/qsone/app.py`,
    `${lib}/site-packages/qsone/fonts/Zain-Regular.ttf`,
    "include/Python.h",
    "lib/libtcl9.0.so",
    "lib/tk9.0/tk.tcl",
    "lib/libpython3.12.so.1.0",
    "bin/python3.12",
    "bin/pip3",
    "bin/uvicorn",
  ]);
  if (process.platform !== "win32") symlinkSync("python3.12", path.join(dir, "bin", "python3"));

  trim(dir, "x86_64-unknown-linux-gnu");

  for (const gone of [
    `${lib}/tkinter`, `${lib}/test`, `${lib}/idlelib`, `${lib}/ensurepip`,
    `${lib}/lib-dynload/readline.cpython-312-x86_64-linux-gnu.so`, `${lib}/lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so`,
    `${lib}/site-packages/pip`, `${lib}/site-packages/pip-26.2.2.dist-info`, `${lib}/site-packages/x/tests`,
    `${lib}/site-packages/x/__pycache__`, `${lib}/site-packages/x/libstatic.a`, "include", "lib/libtcl9.0.so",
    "lib/tk9.0", "bin/pip3", "bin/uvicorn", "bin/python3.12",
  ]) expect(existsSync(path.join(dir, gone)), gone).toBe(false);
  for (const kept of [
    `${lib}/os.py`, `${lib}/lib-dynload/_ssl.cpython-312-x86_64-linux-gnu.so`, `${lib}/site-packages/x/mod.py`,
    `${lib}/site-packages/qsone/app.py`, `${lib}/site-packages/qsone/fonts/Zain-Regular.ttf`, "lib/libpython3.12.so.1.0",
  ]) expect(existsSync(path.join(dir, kept)), kept).toBe(true);
  expect(readdirSync(path.join(dir, "bin"))).toEqual(["python3"]); // the interpreter itself, not a link
  expect(layout(dir, "x86_64-unknown-linux-gnu").python).toBe(path.join(dir, "bin", "python3"));
});

test("trim on Windows drops Tcl/Tk, test modules, import libraries and Scripts", () => {
  const dir = tmp();
  put(dir, [
    "python.exe", "Lib/os.py", "Lib/tkinter/__init__.py", "DLLs/_tkinter.pyd", "DLLs/tcl86t.dll", "DLLs/tk86t.dll",
    "DLLs/_testcapi.pyd", "DLLs/_ssl.pyd", "DLLs/libcrypto-3-x64.dll", "tcl/tcl86t.lib", "libs/python312.lib",
    "Scripts/pip.exe", "Lib/site-packages/x/mod.py",
  ]);
  trim(dir, "x86_64-pc-windows-msvc");
  for (const gone of ["Lib/tkinter", "DLLs/_tkinter.pyd", "DLLs/tcl86t.dll", "DLLs/tk86t.dll", "DLLs/_testcapi.pyd", "tcl", "libs", "Scripts"]) {
    expect(existsSync(path.join(dir, gone)), gone).toBe(false);
  }
  for (const kept of ["python.exe", "Lib/os.py", "DLLs/_ssl.pyd", "DLLs/libcrypto-3-x64.dll", "Lib/site-packages/x/mod.py"]) {
    expect(existsSync(path.join(dir, kept)), kept).toBe(true);
  }
  expect(layout(dir, "x86_64-pc-windows-msvc").python).toBe(path.join(dir, "python.exe"));
});

test("bytecode only: no .py left, every module has a .pyc beside its name, and it imports", () => {
  const lib = path.join(tmp(), "lib");
  const site = path.join(lib, "site-packages");
  put(lib, ["os_like.py", "site-packages/x/__init__.py", "site-packages/x/mod.py", "site-packages/qsone/app.py"]);
  put(lib, ["site-packages/qsone/sandbox/guest/one_io.py", "site-packages/qsone/engine/instructions/lead_qs.txt"]);
  const python = corePython();

  bytecodeOnly(python, lib);

  const files = [];
  const walk = (d) => readdirSync(d, { withFileTypes: true }).forEach((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : files.push(path.relative(lib, path.join(d, e.name)))));
  walk(lib);
  const posix = files.map((f) => f.split(path.sep).join("/")).sort();
  expect(posix.filter((f) => f.endsWith(".py"))).toEqual(["site-packages/qsone/sandbox/guest/one_io.py"]); // the Sandbox reads it as text
  for (const module of ["os_like", "site-packages/x/__init__", "site-packages/x/mod", "site-packages/qsone/app"]) {
    expect(posix).toContain(`${module}.pyc`);
  }
  expect(posix).toContain("site-packages/qsone/engine/instructions/lead_qs.txt");
  expect(posix.some((f) => f.includes("__pycache__"))).toBe(false);

  const run = spawnSync(python, ["-I", "-c", `import sys; sys.path.insert(0, ${JSON.stringify(site)}); import x.mod; print(x.mod.VALUE)`], { encoding: "utf8" });
  expect(run.stdout.trim()).toBe("7");
});

test("the core's data ships with it, and a licensed font never does", () => {
  const site = tmp();
  copyCore(path.join(root, "core", "qsone"), site);
  for (const data of [
    "qsone/engine/instructions/lead_qs.txt", "qsone/engine/instructions/checking_qs.txt",
    "qsone/deliverables/templates/sheet.json", "qsone/export/typst/sheet.typ", "qsone/fonts/Zain-Regular.ttf",
    "qsone/fonts/KumbhSans-Variable.ttf", "qsone/fonts/OFL.txt", "qsone/sandbox/guest/one_io.py", "qsone/__main__.py",
  ]) expect(existsSync(path.join(site, data)), data).toBe(true);
  expect(() => refuseLicensedFonts(site)).not.toThrow();

  put(site, ["qsone/fonts/Thmanyah-Sans-Regular.otf"]);
  expect(() => refuseLicensedFonts(site)).toThrow(/Thmanyah-Sans-Regular\.otf/);
});

test("every runtime.json target has a url and a 64-hex sha256", () => {
  const targets = ["x86_64-pc-windows-msvc", "x86_64-unknown-linux-gnu", "aarch64-apple-darwin", "x86_64-apple-darwin"];
  expect(Object.keys(runtime.targets).sort()).toEqual([...targets].sort());
  for (const [target, { url, sha256 }] of Object.entries(runtime.targets)) {
    expect(url).toMatch(/^https:\/\/github\.com\/astral-sh\/python-build-standalone\/releases\/download\//);
    expect(url).toContain(`cpython-${runtime.python}+${runtime.release}-${target}-install_only_stripped.tar.gz`);
    expect(sha256).toMatch(/^[0-9a-f]{64}$/);
  }
});

test("the smoke test starts the core without any virtual environment", () => {
  const sep = process.platform === "win32" ? ";" : ":";
  const env = cleanEnv({
    PATH: ["/repo/core/.venv/bin", "/usr/bin", "/home/me/.venv/bin"].join(sep),
    VIRTUAL_ENV: "/repo/core/.venv",
    PYTHONPATH: "/repo/core",
    PYTHONHOME: "/x",
    HOME: "/home/me",
  });
  expect(env).toEqual({ PATH: "/usr/bin", HOME: "/home/me" });
});
