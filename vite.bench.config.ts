import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";
import { coreDev } from "./scripts/core-dev.ts";
import { corePython } from "./scripts/python.mjs";

// The test bench (`npm run bench`): the real screen and the real core on port 1442, with the bench's fake AI
// (core/tests/bench) in place of any provider. scripts/bench.mjs sets QSONE_BENCH_DIR to a throwaway folder.
const dir = process.env.QSONE_BENCH_DIR;
if (!dir) throw new Error("QSONE_BENCH_DIR is not set: start the bench with `npm run bench`.");

export default defineConfig({
  root: "ui",
  plugins: [
    react(),
    tailwindcss(),
    coreDev({
      command: [corePython(), "-m", "tests.bench", "--data-dir", path.join(dir, "data"), "--samples", path.join(dir, "samples")],
      logFile: path.join(dir, "core.log"),
    }),
  ],
  server: { host: "127.0.0.1", port: 1442, strictPort: true }, // 1440 is the dev app's
});
