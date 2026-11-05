// The chrome around the canvas, measured in a real browser: the frames shown beside the open chat (never under it, in
// both languages), one message box at the chat's foot, the placeholder whole at every width, the project's name never
// cut and the status folding into "More status" before anything clips, a newly opened frame in visible free space.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { canvasReady, frame, mockCore, small } from "./fixtures";

type Box = { x: number; y: number; width: number; height: number };
const box = async (l: Locator) => (await l.boundingBox())!;
const overlaps = (a: Box, b: Box) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

/** Whether the element's text is all shown: nothing hidden past its edges. */
const whole = (l: Locator) => l.evaluate((el) => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1);

async function covers(page: Page): Promise<Box[]> {
  return page.locator("[data-canvas-cover], .react-flow__minimap").evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    }),
  );
}

for (const language of ["ar", "en"] as const) {
  test(`fit all shows the frames beside the open chat, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const scene = small();
    scene.layout.frames = []; // a first open: every frame placed and fitted
    await mockCore(page, scene, { language });
    await page.goto("/");
    await canvasReady(page);
    const chat = await box(page.locator('aside[data-region="chat"]'));
    for (const node of await page.locator(".react-flow__node").all()) expect(overlaps(await box(node), chat)).toBe(false);
  });

  test(`one message box, at the open chat's foot, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockCore(page, small(), { language });
    await page.goto("/");
    await canvasReady(page);
    const chat = page.locator('aside[data-region="chat"]');
    await expect(page.locator("[data-command-box]")).toHaveCount(1);
    await expect(chat.locator("[data-command-box]")).toBeVisible();
    const input = await box(chat.locator("[data-command-box]"));
    const panel = await box(chat);
    expect(panel.y + panel.height - (input.y + input.height)).toBeLessThan(40);
  });

  for (const width of [800, 940, 1024, 1440]) {
    test(`the placeholder and the top bar are whole at ${width} px, ${language}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const scene = small();
      scene.project.name = language === "ar" ? "برج إداري بالعاصمة الإدارية الجديدة - عينة" : "Administrative tower, New Capital (sample)";
      await mockCore(page, scene, { language });
      await page.goto("/");
      await canvasReady(page);
      // the box shows its whole placeholder, in the chat or floating (the chat folded)
      const input = page.locator("[data-command-box]");
      expect(await whole(input)).toBe(true);
      const mirror = await box(page.locator("[data-command-mirror]"));
      const shown = await box(input);
      expect(Math.abs(mirror.height - shown.height)).toBeLessThan(2);
      // the project's name is never cut
      expect(await whole(page.locator('[data-region="topbar"] [data-region-start] span[dir="auto"]'))).toBe(true);
      // nothing in the top bar spills past its edges, and the status shows whole or folds into More status
      const bar = await box(page.locator('[data-region="topbar"]'));
      for (const item of await page.locator('[data-region="topbar"] button:visible').all()) {
        const b = await box(item);
        expect(b.x).toBeGreaterThanOrEqual(bar.x - 1);
        expect(b.x + b.width).toBeLessThanOrEqual(bar.x + bar.width + 1);
      }
      for (const item of await page.locator('[data-status]:not([aria-hidden="true"])').all()) {
        const strip = await box(item.locator(".."));
        const b = await box(item);
        expect(b.x).toBeGreaterThanOrEqual(strip.x - 1);
        expect(b.x + b.width).toBeLessThanOrEqual(strip.x + strip.width + 1);
      }
    });
  }

  test(`a newly opened frame lands in visible free space, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const scene = small();
    // close enough for the Project files frame to show its list, with room left beside it
    scene.layout.frames = [{ key: "files:all", x: 0, y: 0, w: 360, h: 520, z: 0, collapsed: false }];
    scene.layout.view = { x: language === "ar" ? 900 : 120, y: 40, zoom: 0.8 };
    await mockCore(page, scene, { language });
    await page.goto("/");
    await canvasReady(page);
    await frame(page, "files:all").getByRole("button", { name: /مقايسة العميل - عينة.xlsx/ }).click();
    const opened = frame(page, "file:boq");
    await expect(opened).toBeVisible();
    await page.waitForTimeout(600); // the view's glide to it
    const b = await box(opened);
    const pane = await box(page.locator(".react-flow"));
    expect(b.x).toBeGreaterThanOrEqual(pane.x);
    expect(b.x + b.width).toBeLessThanOrEqual(pane.x + pane.width);
    for (const cover of await covers(page)) expect(overlaps(b, cover)).toBe(false);
  });
}
