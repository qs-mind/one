// The bench's Vite (vite.bench.config.ts: its core, its fake AI, its port) for the real-window walks, which may run in a
// git worktree whose node_modules is a link to the main checkout's: Vite then serves the fonts from there too, or the
// window falls back to the system's fonts and every screenshot shows the wrong type.
// With QSONE_REALAPP_CORE=real (launch({ core: "real" })) the core is the real one with real AI providers instead
// (realcore.py): the same throw-away data folder, keyring's fail backend (ISOLATED_KEYS), no Claude Code, no browser.
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { realpathSync } from "node:fs";
import path from "node:path";
import { defineConfig, mergeConfig, searchForWorkspaceRoot } from "vite";
import bench from "../../vite.bench.config.ts";
import { coreDev } from "../core-dev.ts";
import { corePython, root } from "../python.mjs";
import { ISOLATED_KEYS } from "../smoke-core.mjs";

const fs = { server: { fs: { allow: [searchForWorkspaceRoot(root), realpathSync(path.join(root, "node_modules"))] } } };

function realCore() {
  const dir = process.env.QSONE_BENCH_DIR!;
  Object.assign(process.env, ISOLATED_KEYS); // the core inherits it: never the system key store
  return defineConfig({
    root: "ui",
    resolve: { alias: { "@": path.join(root, "ui", "src") } },
    plugins: [
      react(),
      tailwindcss(),
      coreDev({
        command: [corePython(), path.join(root, "scripts", "realapp", "realcore.py"), "--data-dir", path.join(dir, "data")],
        logFile: path.join(dir, "core.log"),
      }),
    ],
    server: { host: "127.0.0.1", port: Number(process.env.QSONE_BENCH_PORT), strictPort: true, hmr: false },
  });
}

export default mergeConfig(process.env.QSONE_REALAPP_CORE === "real" ? realCore() : bench, fs);
