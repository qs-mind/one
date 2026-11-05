// The test bench: the real app on http://127.0.0.1:1442 with a scripted fake AI (core/tests/bench), never a real
// provider. Its data, sample files and core.log are in <OS temp>/qs-mind-one-bench, fresh each run unless --keep.
// Usage: npm run bench [-- --keep]
import { spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { root } from "./python.mjs";

export const benchDir = path.join(tmpdir(), "qs-mind-one-bench");

if (!process.argv.includes("--keep")) rmSync(benchDir, { recursive: true, force: true });
mkdirSync(benchDir, { recursive: true });
console.log(`QS Mind One bench: ${benchDir} (core.log, data, samples)`);

const env = {
  ...process.env,
  QSONE_BENCH_DIR: benchDir,
  PYTHONPATH: [path.join(root, "core"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
};
const vite = path.join(root, "node_modules", "vite", "bin", "vite.js");
const child = spawn(process.execPath, [vite, "--config", "vite.bench.config.ts"], { cwd: root, env, stdio: "inherit" });
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) process.on(signal, () => child.kill(signal));
child.on("exit", (code) => process.exit(code ?? 1));
