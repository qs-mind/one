import { defineConfig, devices } from "@playwright/test";

// The bench walks (ui/bench): the real screen and the real core with the bench's fake AI, on port 1442. Not the
// mocked e2e tests (playwright.config.ts). One Chromium, one worker: the founder's dev app runs on this machine too.
// Screenshots go to test-results/bench/shots (git-ignored), and to $QSONE_BENCH_SHOTS when it is set.
const port = 1442;

export default defineConfig({
  testDir: "ui/bench",
  outputDir: "test-results/bench/output",
  workers: 1,
  fullyParallel: false,
  timeout: 240_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure", viewport: { width: 1440, height: 900 } },
  webServer: {
    command: "node scripts/bench.mjs",
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
