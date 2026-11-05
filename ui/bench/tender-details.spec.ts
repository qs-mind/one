// The tender day's layout details, on the real app and core with the bench's fake AI: a Deliverable opened from the
// Project Index sits alone (the index closes) with its Amount column and total in sight; item codes show whole; a
// frame that arrives keeps the frames in view whole at a readable zoom; a number's source card stays in the window;
// and the first launch's "Another provider" form comes into view above the step's bar.
// Screenshots: test-results/bench/shots, and $QSONE_BENCH_SHOTS when it is set.
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import type { Locator, Page } from "@playwright/test";
import { texts } from "../src/i18n";
import { expect, test } from "./bench";

const benchPort = Number(process.env.QSONE_BENCH_PORT || 1442);
const settingsFile = path.join(tmpdir(), benchPort === 1442 ? "qs-mind-one-bench" : `qs-mind-one-bench-${benchPort}`, "data", "settings.json");

/** Whether `inner` lies wholly inside `outer` (1 px of rounding). */
async function inside(inner: Locator, outer: { x: number; y: number; width: number; height: number }) {
  const b = await inner.boundingBox();
  return !!b && b.x >= outer.x - 1 && b.y >= outer.y - 1 && b.x + b.width <= outer.x + outer.width + 1 && b.y + b.height <= outer.y + outer.height + 1;
}

/** The frames wholly in the canvas's free part (right of the chat in Arabic), by key. */
async function framesInView(page: Page) {
  const chat = await page.locator('[data-region="chat"]').boundingBox();
  const pane = (await page.locator('[data-region="canvas"]').boundingBox())!;
  const free = chat ? { ...pane, x: chat.x + chat.width, width: pane.x + pane.width - (chat.x + chat.width) } : pane;
  const keys: string[] = [];
  for (const frame of await page.locator("[data-frame]").all()) if (await inside(frame, free)) keys.push((await frame.getAttribute("data-frame"))!);
  return keys;
}

/** The canvas's zoom readout, as a number (79 for «79%»). */
async function zoom(page: Page) {
  const text = await page.locator('[data-region="canvas"]').getByText(/^\d+%$/).first().textContent();
  return Number((text ?? "0").replace("%", ""));
}

test("tender details: the board alone and whole, codes whole, frames kept in view, the source card in the window", async ({ walk, page }) => {
  await walk.start("ar");
  await walk.createProject("تفاصيل المناقصة - عينة");
  await walk.addFiles();
  await page.waitForTimeout(1500);
  const before = await framesInView(page);
  await walk.brief("bench:deliverable Make the priced BOQ and the cover letter");
  await page.waitForTimeout(1500);

  // Item 8: the new frames came in with the ones in view, whole, at a readable zoom
  const after = await framesInView(page);
  expect.soft(before.filter((k) => !after.includes(k)), `frames in view before (${before.join(", ")}) are still in view (${after.join(", ")})`).toEqual([]);
  const pane = (await page.locator('[data-region="canvas"]').boundingBox())!;
  const z = await zoom(page);
  expect.soft(z, "the view stays readable").toBeGreaterThanOrEqual(60);
  const team = page.locator('[data-frame^="team"]').first();
  if (await team.count()) {
    const box = await team.boundingBox();
    const cut = !!box && box.x < pane.x + pane.width && box.x + box.width > pane.x && !(await inside(team, pane));
    expect.soft(cut, "the Team frame is not left half off the screen").toBe(false);
  }
  await walk.shot("frames-after-deliverables");

  // Item 1: from the Project Index the board opens alone; its Amount column and total are in sight
  await page.locator('[data-region="topbar"]').getByRole("button", { name: texts.deliverablesButton.ar, exact: true }).click();
  const index = page.getByRole("region", { name: texts.deliverables.ar });
  await expect(index).toBeVisible();
  await walk.shot("index-open");
  const sheetRow = index.getByRole("button").filter({ hasText: /مقايسة|BOQ/ }).first();
  await sheetRow.click();
  const board = page.locator("[data-deliverable-panel]");
  await expect(board.getByRole("grid")).toBeVisible();
  await page.waitForTimeout(800);
  await expect.soft(index, "the index closed as the board opened").toHaveCount(0);
  const window = { x: 0, y: 0, ...page.viewportSize()! };
  const grid = board.getByRole("grid");
  const headers = grid.getByRole("columnheader");
  const last = headers.nth((await headers.count()) - 1);
  expect.soft(await inside(last, window), "the last column (Amount) is wholly in the window").toBe(true);
  const total = grid.getByRole("row").last();
  expect.soft(await inside(total.getByRole("gridcell").last(), window), "the grand total is wholly in the window").toBe(true);
  await walk.shot("board-from-index");

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
  const saved = JSON.parse(readFileSync(settingsFile, "utf8")) as Record<string, unknown>;
  for (const key of ["setup", "setup_done_at", "ai_consent", "usage_stats", "language"]) delete saved[key];
  writeFileSync(settingsFile, JSON.stringify(saved));
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
});
