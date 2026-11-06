// ONE scales with the screen (ui/src/ui/scale.ts): at 1280×720, 1366×768, 1536×864 and 1920×1080, in Arabic and
// English, the root font-size follows the window (100 % at 1920×1080, 80 % at 1280×720), body text keeps its floor
// (12.5 px English, 13.5 px Arabic), nothing in the top bar runs over another or past its edges, the document and the
// chat fit the window side by side, and the sheet's rows line up with their cells (the virtualised grid places rows
// from the scaled heights, so a cell's text is never cut). The engineer's zoom (Ctrl/Cmd with = - 0) multiplies the
// scale, never fires in a field, and is kept by the core: a reload comes back at it.
import { expect, test, type Locator } from "@playwright/test";
import { texts } from "../src/i18n";
import { documentRegion, mockCore, scaleOf, small, workspaceReady } from "./fixtures";

const SIZES = [
  { width: 1280, height: 720, scale: 0.8 },
  { width: 1366, height: 768, scale: 0.8 + 0.2 * (48 / 360) },
  { width: 1536, height: 864, scale: 0.88 },
  { width: 1920, height: 1080, scale: 1 },
];
const FLOOR = { en: 12.5, ar: 13.5 };
const BODY = { en: 14, ar: 15 };

const box = async (l: Locator) => (await l.boundingBox())!;

for (const language of ["ar", "en"] as const)
  for (const size of SIZES)
    test(`at ${size.width}×${size.height} everything is at the screen's scale and nothing overlaps or is cut, ${language}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await mockCore(page, small(), { language });
      await page.goto("/");
      await workspaceReady(page, page.getByRole("grid"));

      // the root and the body text
      expect(await scaleOf(page)).toBeCloseTo(size.scale, 3);
      const body = await page.evaluate(() => parseFloat(getComputedStyle(document.body).fontSize));
      expect(body).toBeCloseTo(Math.max(FLOOR[language], BODY[language] * size.scale), 1);
      const bar = page.locator('[data-region="topbar"]');
      expect((await box(bar)).height).toBeCloseTo(44 * size.scale, 0);

      // the top bar: each item inside it, none over another, the project's name whole
      const b = await box(bar);
      const items = await bar.locator("button:visible, [data-sample-label]:visible").all();
      const boxes = [];
      for (const item of items) boxes.push(await box(item));
      for (const [i, a] of boxes.entries()) {
        expect(a.x, "inside the bar").toBeGreaterThanOrEqual(b.x - 1);
        expect(a.x + a.width, "inside the bar").toBeLessThanOrEqual(b.x + b.width + 1);
        expect(a.y + a.height, "inside the bar").toBeLessThanOrEqual(b.y + b.height + 1);
        for (const c of boxes.slice(i + 1)) {
          const apart = a.x + a.width <= c.x + 1 || c.x + c.width <= a.x + 1;
          const inside = (a.x >= c.x - 1 && a.x + a.width <= c.x + c.width + 1) || (c.x >= a.x - 1 && c.x + c.width <= a.x + a.width + 1);
          expect(apart || inside, "two items of the top bar run over each other").toBe(true);
        }
      }
      const name = bar.locator('[data-region-start] span[dir="auto"]');
      expect(await name.evaluate((el) => el.scrollWidth <= el.clientWidth + 1), "the project's name is whole").toBe(true);

      // the document and the chat: side by side, inside the window, the chat at its scaled width
      const sheet = await box(page.locator("[data-document-sheet]"));
      const chat = await box(page.locator('aside[data-region="chat"]'));
      expect(sheet.x + sheet.width <= chat.x + 1 || chat.x + chat.width <= sheet.x + 1, "the chat never over the document").toBe(true);
      for (const r of [sheet, chat]) {
        expect(r.x).toBeGreaterThanOrEqual(-1);
        expect(r.x + r.width).toBeLessThanOrEqual(size.width + 1);
        expect(r.y + r.height).toBeLessThanOrEqual(size.height + 1);
      }
      expect(chat.width).toBeCloseTo(320 * size.scale, 0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

      // the sheet: each row as tall as its cells, one under the other, and no cell's text cut
      const grid = documentRegion(page).getByRole("grid");
      const rows = await grid.locator('[role="row"]').all();
      expect(rows.length).toBeGreaterThan(3);
      let bottom: number | undefined;
      for (const row of rows.slice(1, 8)) {
        const r = await box(row);
        if (bottom !== undefined) expect(Math.abs(r.y - bottom), "rows follow one another").toBeLessThanOrEqual(1);
        bottom = r.y + r.height;
        for (const cell of await row.locator('[role="gridcell"]').all()) {
          const c = await box(cell);
          expect(Math.abs(c.y - r.y), "the cell lines up with its row").toBeLessThanOrEqual(1);
          expect(Math.abs(c.height - r.height), "the cell is its row's height").toBeLessThanOrEqual(1);
          expect(await cell.evaluate((el) => el.scrollHeight <= el.clientHeight + 1), "the cell's text is whole").toBe(true);
        }
      }
      // a one-line row of the open document: 32 px at 100 %, its text at the floor below it
      const one = await box(rows[1]!);
      const line = Math.max(FLOOR[language] / BODY[language], size.scale);
      expect(one.height).toBeCloseTo(24 * line + 8 * size.scale, 0);
    });

test("the engineer's zoom: Ctrl and = or -, not in a field, and kept by the core across a reload", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const core = await mockCore(page, small(), { language: "en" });
  await page.goto("/");
  await workspaceReady(page, page.getByRole("grid"));
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Control+Equal");
  await page.keyboard.press("Control+Equal");
  await expect.poll(() => scaleOf(page)).toBeCloseTo(1.2, 3);
  await expect.poll(() => core.zoom).toBe(1.2);
  // in the message box the keys are the box's
  await page.getByRole("textbox", { name: texts.message.en }).click();
  await page.keyboard.press("Control+Minus");
  expect(await scaleOf(page)).toBeCloseTo(1.2, 3);
  await page.reload();
  await workspaceReady(page);
  await expect.poll(() => scaleOf(page)).toBeCloseTo(1.2, 3);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Control+Digit0");
  await expect.poll(() => scaleOf(page)).toBe(1);
  await expect.poll(() => core.zoom).toBe(1);
});
