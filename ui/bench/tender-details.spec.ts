// The tender day's layout details, on the real app and core with the bench's fake AI: a Deliverable picked from the
// document switcher shows in place with its Amount column and total in sight; item codes show whole; a Deliverable
// that arrives leaves the open document where it was; a number's source card stays in the window; and the first
// launch's "Another provider" form comes into view above the step's bar.
// Screenshots: test-results/bench/shots, and $QSONE_BENCH_SHOTS when it is set.
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import type { Locator } from "@playwright/test";
import { texts } from "../src/i18n";
import { expect, test } from "./bench";

const benchPort = Number(process.env.QSONE_BENCH_PORT || 1442);
const settingsFile = path.join(tmpdir(), benchPort === 1442 ? "qs-mind-one-bench" : `qs-mind-one-bench-${benchPort}`, "data", "settings.json");

/** Whether `inner` lies wholly inside `outer` (1 px of rounding). */
async function inside(inner: Locator, outer: { x: number; y: number; width: number; height: number }) {
  const b = await inner.boundingBox();
  return !!b && b.x >= outer.x - 1 && b.y >= outer.y - 1 && b.x + b.width <= outer.x + outer.width + 1 && b.y + b.height <= outer.y + outer.height + 1;
}

test("tender details: the BOQ whole in place, codes whole, the open document kept, the source card in the window", async ({ walk, page }) => {
  await walk.start("ar");
  await walk.createProject("تفاصيل المناقصة - عينة");
  await walk.addFiles();
  await page.waitForTimeout(1500);
  await walk.brief("bench:deliverable Make the priced BOQ and the cover letter");
  await page.waitForTimeout(1500);

  // Item 8: the new Deliverables came in without taking the engineer away from the open document
  await expect.soft(walk.document, "Project files stays the open document").toHaveAttribute("aria-label", texts.projectFiles.ar);
  await walk.shot("document-after-deliverables");

  // Item 1: picked from the switcher, the BOQ shows in place; its Amount column and total are in sight
  await walk.switcher.click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await walk.shot("switcher-open");
  await menu.getByRole("menuitem").filter({ hasText: /مقايسة|BOQ/ }).first().click();
  const board = walk.document;
  await expect(board.getByRole("grid")).toBeVisible();
  await page.waitForTimeout(800);
  await expect.soft(menu, "the switcher closed as the document opened").toHaveCount(0);
  const window = { x: 0, y: 0, ...page.viewportSize()! };
  const grid = board.getByRole("grid");
  const headers = grid.getByRole("columnheader");
  const last = headers.nth((await headers.count()) - 1);
  expect.soft(await inside(last, window), "the last column (Amount) is wholly in the window").toBe(true);
  const total = grid.getByRole("row").last();
  expect.soft(await inside(total.getByRole("gridcell").last(), window), "the grand total is wholly in the window").toBe(true);
  await walk.shot("boq-from-switcher");

  // Item 7: every item code shows whole in its cell
  const cutCodes = await grid.evaluate((g) =>
    [...g.querySelectorAll<HTMLElement>('[role="row"] > [role="gridcell"]:first-child')]
      .filter((cell) => cell.scrollWidth > cell.clientWidth + 1)
      .map((cell) => cell.textContent),
  );
  expect.soft(cutCodes, "no item code is cut").toEqual([]);

  // Item 5: a calculated amount's source card stays wholly in the window, its formula in words
  const amount = grid.getByRole("row").nth(1).getByRole("gridcell").last();
  await amount.click();
  const card = page.getByRole("dialog", { name: texts.sheetSource.ar });
  await expect(card).toBeVisible();
  await page.waitForTimeout(500);
  expect.soft(await inside(card, window), "the source card is wholly in the window").toBe(true);
  await expect.soft(card).not.toContainText("quantity");
  await walk.shot("amount-source-card");
  await page.keyboard.press("Escape");
  walk.finish();
});

test("first launch: Another provider's form comes into view above the step's bar", async ({ walk, page }) => {
  const original = readFileSync(settingsFile, "utf8");
  const saved = JSON.parse(original) as Record<string, unknown>;
  for (const key of ["setup", "setup_done_at", "ai_consent", "usage_stats", "language"]) delete saved[key];
  writeFileSync(settingsFile, JSON.stringify(saved));
  try {
    await page.goto("/");
    walk.lang = "ar";
    await page.getByRole("button", { name: "العربية", exact: true }).click();
    await page.getByRole("button", { name: texts.setupNext.ar, exact: true }).click();
    await page.getByRole("button", { name: texts.setupSkip.ar, exact: true }).click();
    await page.getByRole("button", { name: texts.consentAgree.ar, exact: true }).click();
    await page.getByRole("button", { name: new RegExp(`^${texts.aiLinkStandard.ar}`) }).click();
    await page.waitForTimeout(800); // the step grows to the form, then it scrolls into view
    const field = page.getByLabel(texts.providerName.ar);
    const bar = await page.locator("[data-step-bar]").boundingBox();
    const box = await field.boundingBox();
    expect(box, "the provider's name field is shown").not.toBeNull();
    expect(box!.y + box!.height, "the field sits above the step's bar").toBeLessThanOrEqual(bar!.y);
    expect(box!.y, "the field is in the window").toBeGreaterThanOrEqual(0);
    await walk.shot("first-launch-another-provider");
  } finally {
    writeFileSync(settingsFile, original); // the walks after this one start with ONE set up, pass or fail
  }
});
