// Calm interaction details on the real app and core, with the bench's fake AI: the review tabs' underline lands
// under the chosen tab in Arabic and glides to the next; the canvas toolbar's tips wait, then open at once while warm;
// the palette's highlight sits under the row the arrow keys reach. Screenshots: test-results/bench/shots.
import type { Locator } from "@playwright/test";
import { texts } from "../src/i18n";
import { expect, test } from "./bench";

/** How far apart two boxes' horizontal spans are, in px (0 when the same). */
async function apart(a: Locator, b: Locator) {
  const [x, y] = [await a.boundingBox(), await b.boundingBox()];
  if (!x || !y) return Infinity;
  return Math.abs(x.x - y.x) + Math.abs(x.width - y.width);
}

test("calm details: tab underline, warm tips and the palette's glide, in Arabic", async ({ walk, page }) => {
  await walk.start("ar");
  await walk.createProject("تفاصيل هادية - عينة");
  await walk.addFiles();

  // Warm tips on the zoom bar: nothing at once, the tip after the wait, the neighbour at once
  const zoomOut = page.getByRole("button", { name: texts.zoomOut.ar, exact: true });
  const zoomIn = page.getByRole("button", { name: texts.zoomIn.ar, exact: true });
  const tip = page.locator('[role="tooltip"]');
  await zoomOut.hover();
  await page.waitForTimeout(250);
  await expect(tip).toHaveCount(0);
  await expect(tip).toHaveText(texts.zoomOut.ar, { timeout: 1000 });
  await walk.shot("tip-zoom-out");
  await zoomIn.hover();
  await expect(tip).toHaveText(texts.zoomIn.ar, { timeout: 150 }); // warm: no wait
  await page.mouse.move(700, 300);
  await expect(tip).toHaveCount(0);

  // The palette: the highlight glides to the row the arrow keys reach
  await page.keyboard.press("Control+k");
  const glide = page.locator('[role="dialog"] [data-glide]');
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(300);
  const selected = page.locator('[role="dialog"] [cmdk-item][data-selected="true"]');
  expect(await apart(glide, selected), "the highlight sits under the chosen row").toBeLessThan(2);
  const [g, s] = [await glide.boundingBox(), await selected.boundingBox()];
  expect(Math.abs((g?.y ?? 0) - (s?.y ?? 0))).toBeLessThan(2);
  await walk.shot("palette-glide");
  await page.keyboard.press("Escape");

  // A Deliverable's review tabs: the underline lands under the chosen tab, then glides to the next one
  await walk.brief("bench:deliverable Make the priced BOQ and the cover letter");
  await page.waitForTimeout(1500);
  // the chat's Open glides to the frame on the canvas (DELIVERABLE_CARD_OPENS); the review tabs are in full screen
  await walk.chat.getByRole("button", { name: /^افتح: / }).first().click();
  await page.waitForTimeout(1200);
  const sheet = page.locator('[data-frame^="deliverable:"]').filter({ has: page.getByRole("grid") }).first();
  await sheet.getByRole("button", { name: texts.openFull.ar, exact: true }).click();
  const tabs = page.getByRole("tablist", { name: texts.reviewPanels.ar });
  await expect(tabs).toBeVisible();
  const line = tabs.locator("[data-tab-underline]");
  const chosen = tabs.locator('[role="tab"][aria-selected="true"]');
  await page.waitForTimeout(400);
  expect(await apart(line, chosen), "the line is under the chosen tab").toBeLessThan(2);
  await walk.shot("tabs-changes");
  await tabs.getByRole("tab", { name: texts.reviewVersions.ar }).click();
  await page.waitForTimeout(400);
  expect(await apart(line, chosen), "the line glided under Versions").toBeLessThan(2);
  const versions = await tabs.getByRole("tab", { name: texts.reviewVersions.ar }).boundingBox();
  const first = await tabs.getByRole("tab").first().boundingBox();
  expect(versions!.x, "in Arabic the later tab is to the left").toBeLessThan(first!.x);
  await walk.shot("tabs-versions");
});
