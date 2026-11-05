// The workspace's two approved screens (docs/specs/2026-11-05-workspace-design.md), on the real app and core with the
// bench's fake AI, in Arabic and English, at 1440, 1000 and 640 px: (a) the priced BOQ with one decision waiting, the
// copper dot and «مستنيك قرار واحد» in the top bar, the decision card in the chat, and a number's source card open
// with the supplier's quote and «توريد بس، من غير مصنعية»; (b) the bid letter with nothing waiting. Every number is
// sample data, and the screen says «الأرقام عينة». The PNGs (boq-ar-1440.png, letter-en-640.png, …) go to this
// test's output folder, and to $QSONE_WORKSPACE_SHOTS when it is set.
import { copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import type { Page, TestInfo } from "@playwright/test";
import { count, texts } from "../src/i18n";
import { expect, samplesDir, test } from "./bench";

// the tender's two files, from core/tests/bench/samples.py (write_workspace): the client's BOQ and the supplier's quote
const tender = path.join(path.dirname(samplesDir), "workspace");
const FILES = ["جدول كميات المناقصة - عينة اختبار.xlsx", "عرض أسعار المورد - عينة.pdf"].map((f) => path.join(tender, f));
const SIZES = [
  { width: 1440, height: 900 },
  { width: 1000, height: 800 },
  { width: 640, height: 800 },
];
const words = {
  ar: {
    brief: "bench:workspace سعّر الخرسانة من عرض المورد",
    boq: "جدول كميات مسعر (عينة تجريبية)",
    letter: "خطاب العطاء (عينة تجريبية)",
    notNow: "مش دلوقتي",
  },
  en: {
    brief: "bench:workspace Price the concrete from the supplier's quote",
    boq: "Priced BOQ (bench sample)",
    letter: "Cover letter (bench sample)",
    notNow: "Not now",
  },
} as const;

async function save(page: Page, info: TestInfo, name: string) {
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file });
  const extra = process.env.QSONE_WORKSPACE_SHOTS;
  if (extra) {
    mkdirSync(extra, { recursive: true });
    copyFileSync(file, path.join(extra, `${name}.png`));
  }
}

for (const lang of ["ar", "en"] as const) {
  test(`the workspace's two screens, ${lang}`, async ({ walk, page }, info) => {
    test.setTimeout(300_000);
    const w = words[lang];
    const top = page.locator('[data-region="topbar"]');
    const sample = top.getByText(texts.sampleNumbers[lang], { exact: true });
    await walk.start(lang);
    await walk.createProject(lang === "ar" ? "مبنى إداري - عينة" : "Office building (sample)");
    await walk.addFiles(FILES, false);

    // the Brief: its rows card answered, its question left waiting
    await page.getByRole("textbox", { name: walk.w.message }).fill(w.brief);
    await page.getByRole("button", { name: walk.w.send, exact: true }).click();
    const question = walk.pendingCard().filter({ has: page.locator("fieldset") });
    await expect(async () => {
      const card = walk.pendingCard().filter({ hasNot: page.locator("fieldset") }).first(); // the import's
      if (await card.isVisible()) await walk.answer(card);
      await expect(question.first()).toBeVisible({ timeout: 1000 });
    }).toPass({ timeout: 120_000 });
    // the first project's one-time backup question, put away: the approved screen is the decision's
    const ask = page.getByRole("region", { name: texts.backupTitle[lang] }).filter({ hasText: texts.backupAskFolder[lang] });
    if (await ask.isVisible()) await ask.getByRole("button", { name: texts.backupLater[lang], exact: true }).click();
    await expect(top.locator("[data-waiting-dot]")).toBeVisible();
    await expect(top).toContainText(count("decisionsWaiting", 1, {}, lang));

    // (a) the priced BOQ, a rate's source card open on it
    await expect(async () => expect(await walk.openDocument(w.boq)).toBe(true)).toPass({ timeout: 30_000 });
    await expect(walk.document).toHaveAttribute("aria-label", w.boq);
    const rate = walk.document.getByRole("gridcell", { name: /^3,450/ }).first();
    await expect(rate).toBeVisible();
    for (const size of SIZES) {
      await page.setViewportSize(size);
      await page.waitForTimeout(400);
      if (size.width >= 1000) await expect(sample, "the screen says the numbers are a sample").toBeVisible();
      await expect(walk.chat.locator("[data-waiting]").first().or(page.locator("[data-chat-button]")).first()).toBeVisible();
      if (size.width >= 1000) {
        await question.first().evaluate((el) => el.scrollIntoView({ block: "end" })); // the whole card, its Send too
        await expect(question.first(), "the decision card is in the chat").toBeInViewport();
      }
      await page.keyboard.press("Escape"); // a card left open from the last size
      await rate.scrollIntoViewIfNeeded();
      await rate.click();
      const card = page.getByRole("dialog", { name: texts.sheetSource[lang] }).last();
      await expect(card).toContainText(texts.supplyOnly[lang]);
      await expect(card.locator("blockquote")).toContainText("3450");
      await expect(card.getByRole("button", { name: texts.sourceOpenPage[lang] })).toBeVisible();
      await page.waitForTimeout(300);
      await save(page, info, `boq-${lang}-${size.width}`);
    }
    await page.keyboard.press("Escape");

    // the decision answered, the Brief ends; (b) the bid letter, nothing waiting
    await page.setViewportSize(SIZES[0]!);
    const marks = await walk.chat.getByText(/bench reply|رد تجريبي/).count();
    const card = question.first();
    await card.getByRole("radio", { name: w.notNow }).check();
    await card.getByRole("button", { name: walk.w.send, exact: true }).click();
    await expect(question).toHaveCount(0); // answered, before the walk looks for any other card
    await walk.follow(w.brief, { marks });
    await expect(top).toContainText(texts.nothingWaiting[lang]);
    // the BOQ so far counts as the client's BOQ does: its 5 items, each in the priced BOQ
    await expect(top).toContainText(count("boqItemsOf", 5, { done: 5 }, lang));
    await walk.openDocument(w.letter);
    await expect(walk.document).toHaveAttribute("aria-label", w.letter);
    await expect(walk.document.locator("[data-document-sheet]")).toContainText(w.letter);
    for (const size of SIZES) {
      await page.setViewportSize(size);
      await page.waitForTimeout(400);
      // below 1000 px nothing waiting is said by no dot: the bar keeps its room for the title and the chat button
      if (size.width >= 1000) await expect(top).toContainText(texts.nothingWaiting[lang]);
      await expect(top.locator("[data-waiting-dot]")).toHaveCount(0);
      await save(page, info, `letter-${lang}-${size.width}`);
    }
  });
}
