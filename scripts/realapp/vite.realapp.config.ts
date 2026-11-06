// The bench's Vite (vite.bench.config.ts: its core, its fake AI, its port) for the real-window walks, which may run in a
// git worktree whose node_modules is a link to the main checkout's: Vite then serves the fonts from there too, or the
// window falls back to the system's fonts and every screenshot shows the wrong type.
import { realpathSync } from "node:fs";
import path from "node:path";
import { mergeConfig, searchForWorkspaceRoot } from "vite";
import bench from "../../vite.bench.config.ts";
import { root } from "../python.mjs";

export default mergeConfig(bench, {
  server: { fs: { allow: [searchForWorkspaceRoot(root), realpathSync(path.join(root, "node_modules"))] } },
});
