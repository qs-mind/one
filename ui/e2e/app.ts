// Helpers for the end-to-end tests: the app against the fake core in the browser (ui/fake.html, served by
// `vite --mode ui`; see playwright.config.ts). msw's Service Worker answers every /api call with sample data, so no
// test starts a core, reaches the network or calls an AI. Each test records console and page errors and fails on them.
import { copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test as base, type Page, type TestInfo } from "@playwright/test";

export type Lang = "ar" | "en";
export type Theme = "light" | "dark";
type Scene = { lang?: Lang; theme?: Theme; first?: "" | "profile" | "upgrade"; scenario?: string };

/** The sample tender with a team and a room (api/samples.json). */
export const TENDER = "5a000000000000000000000000000002";

/** Opens `address` (after the hash) in the scene asked for, and waits for its place. */
export async function open(page: Page, address: string, scene: Scene = {}) {
  const ask = new URLSearchParams();
  for (const [key, value] of Object.entries(scene)) if (value !== undefined) ask.set(key, value);
  await page.goto(`/fake.html?${ask}#${address}`);
  await expect(page.locator("[data-place]").first()).toBeVisible();
}

/** The page is no wider than the window: nothing scrolls sideways. */
export async function noSidewaysScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "the page scrolls sideways").toBeLessThanOrEqual(0);
}

/** Beside the rail only the place scrolls, never the window (the rail would scroll away with it). */
export async function windowStill(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollHeight - document.documentElement.clientHeight);
  expect(over, "the window itself scrolls").toBeLessThanOrEqual(0);
}

/** A screenshot in the test's output folder, copied to $QSONE_SHOTS when it is set. */
export async function shot(page: Page, info: TestInfo, name: string) {
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  const extra = process.env.QSONE_SHOTS;
  if (extra) {
    mkdirSync(extra, { recursive: true });
    copyFileSync(file, path.join(extra, `${name}.png`));
  }
}

export const test = base.extend<{ errors: string[] }>({
  errors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(`console error: ${m.text().slice(0, 400)}`);
      });
      page.on("pageerror", (e) => errors.push(`page error: ${e.message.slice(0, 400)}`));
      await use(errors);
      expect(errors, errors.join("\n")).toEqual([]);
    },
    { auto: true },
  ],
});
export { expect };
