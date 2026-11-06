// ONE scales with the screen (ui/src/ui/scale.ts): at 1280×720, 1366×768, 1536×864 and 1920×1080, in Arabic and
// English, the root font-size follows the window (100 % at 1920×1080, 80 % at 1280×720), body text keeps its floor
// (12.5 px English, 13.5 px Arabic), nothing in the top bar runs over another or past its edges, the document and the
// chat fit the window side by side, and the sheet's rows line up with their cells (the virtualised grid places rows
// from the scaled heights, so a cell's text is never cut). The engineer's zoom (Ctrl/Cmd with = - 0) multiplies the
// scale, never fires in a field, and is kept by the core: a reload comes back at it.
import { expect, test, type Locator } from "@playwright/test";
import { texts } from "../src/i18n";
import { documentRegion, mockCore, scaleOf, shownWhole, small, workspaceReady } from "./fixtures";

const SIZES = [
  { width: 1280, height: 720, scale: 0.8 },
  { width: 1366, height: 768, scale: 0.8 + 0.2 * (86 / 640) }, // by its width: heights go from 650 to 1000
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

// The engineer's zoom on the smallest window: the layout's widths follow it (at 150 % a 1280 px window is laid out as
// 853 px is: the chat is a panel from the top bar; at 80 % as 1600 px is), and still nothing runs over or is cut.
for (const language of ["ar", "en"] as const)
  for (const zoom of [1.5, 0.8])
    test(`at 1280×720 zoomed to ${zoom * 100} % the layout follows the zoom, and nothing overlaps, is cut or runs over, ${language}`, async ({ page }) => {
      const size = { width: 1280, height: 720 };
      await page.setViewportSize(size);
      const core = await mockCore(page, small(), { language });
      core.zoom = zoom; // the saved zoom, read before ONE opens
      await page.goto("/");
      await workspaceReady(page, page.getByRole("grid"));
      expect(await scaleOf(page)).toBeCloseTo(0.8 * zoom, 3);

      // the top bar: each item inside it, whole, none over another
      const bar = page.locator('[data-region="topbar"]');
      const b = await box(bar);
      const items = await bar.locator("button:visible, [data-sample-label]:visible").all();
      expect(items.length).toBeGreaterThan(1);
      const boxes = [];
      for (const item of items) {
        boxes.push(await box(item));
        expect(await shownWhole(item), `«${await item.textContent()}» is seen whole`).toBe(true);
      }
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

      // the document and the chat fit the window: side by side at 80 %, the chat a panel over the document at 150 %
      const inWindow = (r: { x: number; y: number; width: number; height: number }) => {
        expect(r.x).toBeGreaterThanOrEqual(-1);
        expect(r.y).toBeGreaterThanOrEqual(-1);
        expect(r.x + r.width).toBeLessThanOrEqual(size.width + 1);
        expect(r.y + r.height).toBeLessThanOrEqual(size.height + 1);
      };
      const sheet = await box(page.locator("[data-document-sheet]"));
      inWindow(sheet);
      const chat = page.locator('aside[data-region="chat"]');
      if (size.width / zoom < 1000) {
        await expect(chat).toHaveCount(0);
        await page.locator("[data-chat-button]").click();
        await expect(chat).toBeVisible();
      } else {
        const c = await box(chat);
        expect(sheet.x + sheet.width <= c.x + 1 || c.x + c.width <= sheet.x + 1, "the chat never over the document").toBe(true);
      }
      inWindow(await box(chat));
      // the message box and its buttons (its chips unfold when it is in use), whole inside the chat
      const message = chat.getByRole("textbox", { name: texts.message[language] });
      await message.click();
      await page.waitForTimeout(400);
      expect(await shownWhole(message)).toBe(true);
      for (const button of await chat.locator('[data-region="command"] button:visible').all())
        expect(await shownWhole(button), `«${await button.getAttribute("aria-label") ?? await button.textContent()}» is seen whole`).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "no scroll sideways").toBe(true);

      // the sheet's header cells keep their words, and no cell's text is cut
      const grid = documentRegion(page).getByRole("grid");
      for (const header of await grid.locator('[role="columnheader"]:visible').all())
        expect(await header.evaluate((el) => el.scrollHeight <= el.clientHeight + 1), "the header's text is whole").toBe(true);
      for (const cell of await grid.locator('[role="row"]').nth(1).locator('[role="gridcell"]').all())
        expect(await cell.evaluate((el) => el.scrollHeight <= el.clientHeight + 1), "the cell's text is whole").toBe(true);
    });

// The smallest text keeps a floor of its own however far the screen shrinks: text-xs never under 12 px, and Arabic
// text-sm never under 13 px (its dots and marks), here at 1280×720 zoomed out to 80 % (the root at 10.24 px).
for (const language of ["ar", "en"] as const)
  test(`at 1280×720 and 80 % text-xs is 12 px and text-sm ${language === "ar" ? "13" : "12.5"} px, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    const core = await mockCore(page, small(), { language });
    core.zoom = 0.8;
    await page.goto("/");
    await workspaceReady(page);
    expect(await scaleOf(page)).toBeCloseTo(0.64, 3);
    const sizes = await page.evaluate(() =>
      Object.fromEntries(
        ["text-xs", "text-sm"].map((name) => {
          const span = document.createElement("span");
          span.className = name;
          span.textContent = "x";
          document.body.append(span);
          const px = parseFloat(getComputedStyle(span).fontSize);
          span.remove();
          return [name, px];
        }),
      ),
    );
    expect(sizes["text-xs"]).toBeCloseTo(12, 2);
    expect(sizes["text-sm"]).toBeCloseTo(language === "ar" ? 13 : 12.5, 2);
    const body = await page.evaluate(() => parseFloat(getComputedStyle(document.body).fontSize));
    expect(body).toBeCloseTo(FLOOR[language], 1);
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
