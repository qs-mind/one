// The audit's layout fixes on the real app and core, with the bench's fake AI, in Arabic: the source card stays on
// screen above everything, Arrange by stage shows every frame clear of the chat, the work log names each agent once,
// full screen has one exit, More's labels say what they open, AI settings never scroll sideways, and at 1000 px the
// chat takes at most a third. Each step takes a screenshot, fix-<item>-<phase>.png in $QSONE_FIX_SHOTS
// ($QSONE_FIX_PHASE, "after" by default), so the same walk shows a screen before and after a fix.
import type { Locator } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { texts } from "../src/i18n";
import { expect, test } from "./bench";

const out = process.env.QSONE_FIX_SHOTS ?? path.join("test-results", "bench", "fixed");
const phase = process.env.QSONE_FIX_PHASE ?? "after";
const after = phase === "after";

test("audit fixes, in Arabic", async ({ walk, page }) => {
  test.setTimeout(480_000);
  mkdirSync(out, { recursive: true });
  const shot = async (item: string, el?: Locator) => void (await (el ?? page).screenshot({ path: path.join(out, `fix-${item}-${phase}.png`) }));
  const failed: string[] = [];
  // before a fix the screen may not have what the check looks for: the walk goes on and says what it missed
  const step = async (name: string, fn: () => Promise<void>) => {
    try {
      await fn();
    } catch (error) {
      failed.push(`${name}: ${String(error).split("\n")[0]}`);
    }
  };
  const top = page.locator('[data-region="topbar"]');
  const more = () => top.getByRole("button", { name: texts.more.ar, exact: true }).click();

  await walk.start("ar");
  await walk.createProject("برج الأندلس - عينة");
  await walk.addFiles();
  await step("C11", () => shot("C11"));
  await walk.brief("bench:deliverable Make the priced BOQ and the cover letter");
  await page.waitForTimeout(1500);
  page.setDefaultTimeout(8000); // a step whose control is not there (before its fix) fails fast and the walk goes on

  await step("R5", async () => {
    // the log speaks the Brief's language: the bench's Brief is in English
    await walk.chat.getByRole("button", { name: /^(اشتغل|Worked for)/ }).last().click({ timeout: 5000 });
    await page.waitForTimeout(500);
    await shot("R5", walk.chat);
  });

  await step("C12", async () => {
    await page.getByRole("button", { name: texts.arrangeByStage.ar, exact: true }).click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    await shot("C12");
    if (!after) return;
    // every frame in sight, none under the open chat
    const chat = (await walk.chat.boundingBox())!;
    for (const frame of await page.locator(".react-flow__node").all()) {
      const box = await frame.boundingBox();
      if (!box) continue;
      expect.soft(box.x + box.width <= chat.x || box.x >= chat.x + chat.width, "a frame is clear of the chat").toBe(true);
    }
    await expect.soft(page.getByRole("toolbar", { name: texts.zoomControls.ar }).getByRole("button", { name: texts.fitAll.ar })).toBeVisible();
  });

  const sheet = page.locator('[data-frame^="deliverable:"]').filter({ has: page.getByRole("grid") }).first();
  await step("R9", async () => {
    await walk.chat.getByRole("button", { name: /^افتح: / }).first().click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    await shot("R9");
  });

  await step("B3", async () => {
    await sheet.getByRole("gridcell", { name: "4,100.00", exact: true }).first().click({ timeout: 5000 });
    await page.waitForTimeout(600);
    await shot("B3");
    if (!after) return;
    const card = page.getByRole("dialog").last();
    const box = (await card.boundingBox())!;
    const view = page.viewportSize()!;
    expect.soft(box.y >= 0 && box.y + box.height <= view.height && box.x >= 0 && box.x + box.width <= view.width, "the source card is on screen").toBe(true);
    await expect.soft(card.getByRole("button", { name: texts.sourceOpenFile.ar })).toBeInViewport();
    await page.keyboard.press("Escape");
  });

  await step("C13", async () => {
    await page.keyboard.press("Control+k");
    await page.waitForTimeout(500);
    await shot("C13");
    await page.keyboard.press("Escape");
  });

  await step("R8", async () => {
    await sheet.getByRole("button", { name: texts.openFull.ar, exact: true }).click({ timeout: 5000 });
    await page.waitForTimeout(800);
    await shot("R8");
    if (after) {
      await expect.soft(page.getByRole("button", { name: texts.sheetLeaveFullScreen.ar })).toHaveCount(0);
      await expect.soft(page.getByRole("tab", { name: texts.reviewCloseOut.ar })).toBeVisible();
    }
  });

  await step("C14", async () => {
    await page.getByRole("button", { name: texts.exportExcel.ar, exact: true }).click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    await shot("C14");
    await page.getByRole("button", { name: texts.close.ar, exact: true }).first().click();
    await page.waitForTimeout(600);
  });

  await step("R10", async () => {
    await more();
    await page.waitForTimeout(300);
    await shot("R10");
  });

  await step("R13", async () => {
    await page.getByRole("button", { name: texts.ai.ar, exact: true }).click({ timeout: 5000 });
    await page.waitForTimeout(800);
    await expect(page.getByRole("heading", { name: texts.aiTitle.ar }).first()).toBeVisible();
    await shot("R13");
    if (after) {
      // wherever AI settings open, nothing on the page that scrolls does so sideways (the canvas pans, it never scrolls)
      const sideways = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("body *")]
          .filter((x) => !x.closest(".react-flow"))
          .filter((x) => ["auto", "scroll"].includes(getComputedStyle(x).overflowX) && x.scrollWidth > x.clientWidth + 1)
          .map((x) => x.className.slice(0, 60)),
      );
      expect.soft(sideways, "nothing scrolls sideways").toEqual([]);
    }
    await page.keyboard.press("Escape");
  });

  await step("C10", async () => {
    await page.keyboard.press("Control+k");
    await page.getByRole("combobox").fill(texts.projectTeam.ar);
    await page.getByRole("option", { name: new RegExp(texts.projectTeam.ar) }).first().click({ timeout: 5000 });
    await page.waitForTimeout(1200);
    await shot("C10");
  });

  await step("C21", async () => {
    await page.setViewportSize({ width: 1000, height: 800 });
    await page.waitForTimeout(800);
    await shot("C21");
    if (after) {
      const chat = (await walk.chat.boundingBox())!;
      expect.soft(chat.width, "the chat takes at most a third of 1000 px").toBeLessThanOrEqual(1000 / 3 + 1);
    }
    await more();
    await page.waitForTimeout(300);
    await shot("C21-more");
    await page.keyboard.press("Escape");
  });

  if (failed.length) console.log(`steps that did not run (${phase}):\n${failed.join("\n")}`);
  if (after) expect(failed, "every step ran").toEqual([]);
});
