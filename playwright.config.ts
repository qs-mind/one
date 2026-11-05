import { defineConfig, devices } from "@playwright/test";

// End-to-end tests (Plan 7) run against `vite preview` of the built screen. Every /api call is answered by the
// fixtures in ui/e2e/fixtures.ts, and `vite preview` does not run the dev plugin, so the core never starts.
// Chromium and WebKit (the closest free stand-in for WebKitGTK); the @perf run is its own project, by hand only.
const port = Number(process.env.QSONE_E2E_PORT || 1441); // another worktree's e2e run may hold 1441

export default defineConfig({
  testDir: "ui/e2e",
  forbidOnly: !!process.env.CI,
  workers: 1, // one browser at a time: this machine and the CI runners share their memory
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  webServer: {
    command: `npm run build && npx vite preview --host 127.0.0.1 --port ${port} --strictPort`,
    port,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] }, grepInvert: /@perf/ },
    { name: "webkit", use: { ...devices["Desktop Safari"] }, grepInvert: /@perf/ },
    { name: "perf", use: { ...devices["Desktop Chrome"] }, grep: /@perf/ },
  ],
});
