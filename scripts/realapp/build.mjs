// Builds the ONE desktop debug binary that the real-window walks drive: the dev window (it loads a Vite server),
// with its own identifier, so it never hands over to the founder's ONE (single-instance) or reads his window state,
// and its own target folder, so it never rebuilds the founder's `tauri dev` binary.
// Usage: node scripts/realapp/build.mjs [port]   (the Vite port the window loads; it is built into the binary)
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
export const IDENTIFIER = "app.qsmind.one.realapp";
export const DEFAULT_PORT = 1477; // not 1440 (the founder's dev app), 1442 (the bench), 1702 or 18301 (another test agent)
const targetDir = path.join(root, "desktop", "target", "realapp"); // git-ignored with desktop/target/

export function binaryPath() {
  return path.join(targetDir, "debug", process.platform === "win32" ? "qs-mind-one.exe" : "qs-mind-one");
}

/** The config merged over desktop/tauri.conf.json at build time (tauri-build reads TAURI_CONFIG). */
export function tauriConfig(port) {
  return { identifier: IDENTIFIER, build: { devUrl: `http://127.0.0.1:${port}`, beforeDevCommand: "" } };
}

/** `cargo build` of the desktop crate for this port; a no-op when nothing changed. Throws when it fails. */
export function build(port = DEFAULT_PORT, { quiet = false } = {}) {
  const result = spawnSync("cargo", ["build", "--manifest-path", path.join(root, "desktop", "Cargo.toml"), "-j", "6"], {
    cwd: path.join(root, "desktop"),
    env: { ...process.env, CARGO_TARGET_DIR: targetDir, TAURI_CONFIG: JSON.stringify(tauriConfig(port)) },
    stdio: quiet ? ["ignore", "ignore", "pipe"] : "inherit",
    encoding: "utf8",
  });
  if (result.status !== 0) throw new Error(`cargo build failed (${result.status})${quiet ? `\n${result.stderr?.slice(-4000)}` : ""}`);
  return binaryPath();
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  console.log(build(Number(process.argv[2] || DEFAULT_PORT)));
}
