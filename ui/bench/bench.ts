// Helpers for the bench walks: the real app and the real core with the fake AI of core/tests/bench (see
// playwright.bench.config.ts). A walk records every console error, page error and failed /api request, and fails with
// them at the end. The bench core starts with first launch's language and AI passed and the profile empty, as someone
// upgrading: first launch is step 2 only.
import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
import path from "node:path";
import { expect, test as base, type Page, type TestInfo } from "@playwright/test";

const shotsDir = path.join("test-results", "bench", "shots");

export class Walk {
  readonly problems: string[] = [];
  private n = 0;

  constructor(
    readonly page: Page,
    private readonly info: TestInfo,
  ) {
    page.on("console", (m) => {
      if (m.type() === "error") this.problems.push(`console error: ${m.text().slice(0, 500)} (at ${page.url()})`);
    });
    page.on("pageerror", (e) => this.problems.push(`page error: ${e.message.slice(0, 500)}`));
    page.on("response", (r) => {
      if (r.url().includes("/api/") && r.status() >= 400)
        this.problems.push(`HTTP ${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`);
    });
    page.on("requestfailed", (r) => {
      const why = r.failure()?.errorText ?? "";
      // a stream the page itself closes (leaving a place, a reload) is aborted, not failed
      if (r.url().includes("/api/") && !why.includes("ERR_ABORTED"))
        this.problems.push(`request failed: ${r.method()} ${new URL(r.url()).pathname}: ${why}`);
    });
  }

  /** The place on screen (its data-place). */
  place(name: string) {
    return this.page.locator(`[data-place="${name}"]`);
  }

  /** A full-page screenshot in test-results/bench/shots, copied to $QSONE_BENCH_SHOTS when it is set. */
  async shot(name: string) {
    this.n += 1;
    const slug = this.info.title.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
    const file = path.join(shotsDir, `${slug}-${String(this.n).padStart(2, "0")}-${name}.png`);
    mkdirSync(shotsDir, { recursive: true });
    await this.page.screenshot({ path: file, fullPage: true });
    const extra = process.env.QSONE_BENCH_SHOTS;
    if (extra) {
      mkdirSync(extra, { recursive: true });
      const next = readdirSync(extra).filter((f) => f.endsWith(".png")).length + 1;
      copyFileSync(file, path.join(extra, `${String(next).padStart(2, "0")}-${slug}-${name}.png`));
    }
    return file;
  }

  /** Every problem met: console errors, failed /api requests, each on its own line. */
  finish() {
    expect.soft(this.problems, `problems met in the walk:\n${this.problems.join("\n")}`).toEqual([]);
  }
}

export const test = base.extend<{ walk: Walk }>({
  walk: async ({ page }, use, info) => {
    const walk = new Walk(page, info);
    await use(walk);
    walk.finish();
  },
});
export { expect };
