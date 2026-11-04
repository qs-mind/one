// Find the core's virtual-environment Python, or run it with the given arguments from the repository root.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export function corePython() {
  const venv = path.join(root, "core", ".venv");
  const python = process.platform === "win32" ? path.join(venv, "Scripts", "python.exe") : path.join(venv, "bin", "python");
  if (!existsSync(python)) throw new Error(`No core environment at ${venv}. See README.md to create it.`);
  return python;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = spawnSync(corePython(), process.argv.slice(2), { cwd: root, stdio: "inherit" });
  process.exit(result.status ?? 1);
}
