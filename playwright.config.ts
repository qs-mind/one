import { defineConfig, devices } from "@playwright/test";

// End-to-end tests (ui/e2e) run against the fake-core page (ui/fake.html) of `vite --mode ui`: msw's Service Worker
// answers every /api call with sample data, so the core never starts and no test reaches the network.
// Chromium and WebKit (the closest free stand-in for WebKitGTK).
const port = Number(process.env.QSONE_E2E_PORT || 1441); // another worktree's e2e run may hold 1441

export default defineConfig({
  testDir: "ui/e2e",
  forbidOnly: !!process.env.CI,
  workers: 1, // one browser at a time: this machine and the CI runners share their memory
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure", viewport: { width: 1440, height: 900 } },
  webServer: {
    command: `npx vite --mode ui --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}/fake.html`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "webkit", use: { ...devices["Desktop Safari"], viewport: { width: 1440, height: 900 } } },
  ],
});
