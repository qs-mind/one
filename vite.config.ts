import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { msw } from "msw/vite";
import { searchForWorkspaceRoot } from "vite";
import { defineConfig } from "vitest/config";
import { coreDev } from "./scripts/core-dev.ts";

// In development the Vite server starts the core and forwards /api to it with the launch secret,
// so the browser preview and the Tauri window reach the core the same way and never hold the secret.
// `vite --mode ui` (npm run dev:ui) serves the app against the fake core at /fake.html instead: msw's Service Worker
// (served by its Vite plugin) answers every call, and no core starts.
export default defineConfig(({ command, mode }) => ({
  root: "ui",
  resolve: { alias: { "@": fileURLToPath(new URL("./ui/src", import.meta.url)) } },
  plugins: [
    react(),
    tailwindcss(),
    ...(command === "serve" && mode === "ui" ? [msw({ mode: "worker-only" })] : []),
    ...(command === "serve" && mode !== "ui" && !process.env.VITEST ? [coreDev()] : []),
  ],
  server: {
    port: 1440, // Tawreed uses 1430, Quantix 1420; all can run side by side
    strictPort: true,
    // a git worktree's node_modules may be a link to the main checkout's: the fonts are served from there too
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), realpathSync(fileURLToPath(new URL("./node_modules", import.meta.url)))] },
  },
  build: { outDir: "../dist", emptyOutDir: true },
  test: {
    root: ".",
    environment: "jsdom",
    include: ["ui/src/**/*.test.{ts,tsx}", "scripts/**/*.test.{ts,mjs}"],
    setupFiles: ["ui/src/test-setup.ts"],
    testTimeout: 20000, // a busy machine or CI runner must not fail a correct test
  },
}));
