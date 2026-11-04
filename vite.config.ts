import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { coreDev } from "./scripts/core-dev.ts";

// In development the Vite server starts the core and forwards /api to it with the launch secret,
// so the browser preview and the Tauri window reach the core the same way and never hold the secret.
export default defineConfig(({ command }) => ({
  root: "ui",
  plugins: [react(), tailwindcss(), ...(command === "serve" && !process.env.VITEST ? [coreDev()] : [])],
  server: {
    port: 1440, // Tawreed uses 1430, Quantix 1420; all can run side by side
    strictPort: true,
  },
  build: { outDir: "../dist", emptyOutDir: true },
  test: {
    root: ".",
    environment: "jsdom",
    include: ["ui/src/**/*.test.{ts,tsx}", "scripts/**/*.test.ts"],
    setupFiles: ["ui/src/test-setup.ts"],
    testTimeout: 20000, // a busy machine or CI runner must not fail a correct test
  },
}));
