// Smoke test of a packaged core: starts `<python> -I -m qsone` the way the release shell does (free port, fresh
// secret, --exit-with-stdin, a fresh data folder, an environment without any virtual environment or PYTHON*
// variable but one that keeps it off the system key store), then checks /health within 60 s, /about (version from package.json; 401 without the secret),
// /about/native (every native library loads) and that the core exits 0 within 15 s once stdin closes.
//
//   node scripts/smoke-core.mjs [<python>]     (default: build/core's Python for this machine)
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { hostTarget, layout } from "./package-core.mjs";
import { root } from "./python.mjs";

// Never the engineer's key store: with keyring's "fail" backend the core keeps its keys in keystore.json inside the
// temporary data folder (core/qsone/keystore.py). On 5 Nov 2026 a smoke run with the real key store wrote over the key
// of the engineer's own Engineer Records. scripts/keystore-isolation.test.mjs checks every script that starts a core.
export const ISOLATED_KEYS = { PYTHON_KEYRING_BACKEND: "keyring.backends.fail.Keyring" };

const NATIVE = ["sqlcipher", "sqlite_vec", "pdfium", "tokenizers", "wasmtime", "typst", "keyring_backend", "cryptography", "drawings"];

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

/** The parent's environment without what would make the packaged Python find another one's packages. */
export function cleanEnv(env = process.env) {
  const sep = process.platform === "win32" ? ";" : ":";
  const venv = env.VIRTUAL_ENV;
  const out = {};
  for (const [key, value] of Object.entries(env)) {
    if (/^(PYTHON|VIRTUAL_ENV|CONDA|UV_|PIP_)/i.test(key) || value === undefined) continue;
    out[key] = value;
  }
  const pathKey = Object.keys(out).find((k) => k.toUpperCase() === "PATH");
  if (pathKey) {
    out[pathKey] = out[pathKey]
      .split(sep)
      .filter((p) => !/[\\/]\.?venv[\\/]/i.test(`${p}/`) && !(venv && p.startsWith(venv)))
      .join(sep);
  }
  return out;
}

export async function smoke(python) {
  const port = await freePort();
  const secret = randomBytes(32).toString("hex");
  const data = mkdtempSync(path.join(tmpdir(), "qsone-smoke-"));
  const version = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8")).version;
  const base = `http://127.0.0.1:${port}`;
  const auth = { Authorization: `Bearer ${secret}` };
  const env = { ...cleanEnv(), ...ISOLATED_KEYS, QSONE_SECRET: secret, QSONE_RELEASE: "1", PYTHONDONTWRITEBYTECODE: "1", PYTHONUTF8: "1" };
  const started = Date.now();
  const child = spawn(python, ["-I", "-X", "utf8", "-B", "-m", "qsone", "--port", String(port), "--exit-with-stdin", "--data-dir", data], {
    cwd: data, // never the repository, so nothing can come from core/qsone
    env,
    stdio: ["pipe", "inherit", "inherit"],
  });
  let exit;
  const exited = new Promise((resolve) => child.once("exit", (code, signal) => resolve((exit = { code, signal }))));
  const fail = (text) => {
    child.kill();
    throw new Error(text);
  };
  try {
    for (;;) {
      if (exit) fail(`the core stopped before it answered /health (exit ${exit.code ?? exit.signal})`);
      if (Date.now() - started > 60_000) fail("/health did not answer within 60 s");
      try {
        if ((await fetch(`${base}/health`, { headers: auth })).ok) break;
      } catch {
        // not listening yet
      }
      await new Promise((r) => setTimeout(r, 100));
    }
    const startSeconds = (Date.now() - started) / 1000;

    const about = await (await fetch(`${base}/about`, { headers: auth })).json();
    if (about.version !== version || about.release !== true) fail(`/about said ${JSON.stringify(about)}, expected ${version} in release`);
    const refused = await fetch(`${base}/about`);
    if (refused.status !== 401) fail(`/about without the secret answered ${refused.status}, not 401`);

    const nativeResponse = await fetch(`${base}/about/native`, { headers: auth });
    if (!nativeResponse.ok) fail(`/about/native answered ${nativeResponse.status}: ${await nativeResponse.text()}`);
    const native = await nativeResponse.json();
    const missing = NATIVE.filter((k) => typeof native[k] !== "string" || !native[k]);
    // onnxruntime has no Intel Mac wheel: search there is by words only
    const onnxOptional = process.platform === "darwin" && process.arch === "x64";
    if (!native.onnxruntime && !onnxOptional) missing.push("onnxruntime");
    if (missing.length) fail(`/about/native did not load: ${missing.join(", ")} (${JSON.stringify(native)})`);

    const stopping = Date.now();
    child.stdin.end();
    const done = await Promise.race([exited, new Promise((r) => setTimeout(() => r(undefined), 15_000))]);
    if (!done) fail("the core did not exit within 15 s of stdin closing");
    if (done.code !== 0) throw new Error(`the core exited with ${done.code ?? done.signal} when stdin closed, not 0`);
    return { startSeconds, stopSeconds: (Date.now() - stopping) / 1000, about, native };
  } finally {
    if (!exit) child.kill();
    rmSync(data, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const python = path.resolve(process.argv[2] ?? layout(path.join(root, "build", "core"), hostTarget()).python);
  smoke(python).then(
    ({ startSeconds, stopSeconds, about, native }) => {
      console.log(`smoke: ${python} answered /health in ${startSeconds.toFixed(2)} s; version ${about.version}`);
      console.log(`smoke: native ${JSON.stringify(native)}`);
      console.log(`smoke: exited 0 ${stopSeconds.toFixed(2)} s after stdin closed`);
    },
    (error) => {
      console.error(`smoke failed: ${error.message}`);
      process.exit(1);
    },
  );
}
