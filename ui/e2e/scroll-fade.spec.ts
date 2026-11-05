// Scroll edges in a real browser, Chromium and WebKit (the stand-in for Linux's WebKitGTK): the palette's list fades
// only at an edge with more beyond it, and the fade is a real mask the engine draws.
import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test, type Locator } from "@playwright/test";
import { canvasReady, mockCore, small } from "./fixtures";

const edges = (area: Locator) =>
  area.evaluate((el) => {
    const style = getComputedStyle(el);
    return {
      top: el.hasAttribute("data-more-top"),
      bottom: el.hasAttribute("data-more-bottom"),
      mask: style.maskImage || style.getPropertyValue("-webkit-mask-image"),
    };
  });

test("the palette's list fades at the edge with more beyond it, and only there", async ({ page }, info) => {
  await page.setViewportSize({ width: 1000, height: 420 }); // the list (half the window high) has more than it shows
  await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  await page.locator('[data-region="topbar"]').getByRole("button").first().focus();
  await page.keyboard.press(`${process.platform === "darwin" ? "Meta" : "Control"}+KeyK`);
  const list = page.locator("[cmdk-list]");
  await expect(list).toBeVisible();
  expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);

  await expect.poll(() => edges(list)).toMatchObject({ top: false, bottom: true });
  expect((await edges(list)).mask).toContain("linear-gradient");
  const dir = path.join("test-results", "e2e-shots");
  mkdirSync(dir, { recursive: true });
  await page.waitForTimeout(400);
  await list.screenshot({ path: path.join(dir, `scroll-fade-bottom-${info.project.name}.png`) });

  await list.evaluate((el) => el.scrollTo({ top: (el.scrollHeight - el.clientHeight) / 2 }));
  await expect.poll(() => edges(list)).toMatchObject({ top: true, bottom: true });
  await list.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
  await expect.poll(() => edges(list)).toMatchObject({ top: true, bottom: false });

  // a search that leaves one line: nothing to fade, so nothing hides it
  await page.keyboard.type("مقارنة عروض");
  await expect(page.getByRole("option", { name: "مقارنة عروض الموردين - عينة" })).toBeVisible();
  await expect.poll(() => edges(list)).toMatchObject({ top: false, bottom: false, mask: "none" });
});
