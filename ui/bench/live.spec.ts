// ONE saves and checks as you go, on the real app and core: in Connect AI, a pasted key is checked at once (the
// bench's own check, never Anthropic: core/tests/bench/__main__.py), refused or working, and Next waits in its place;
// in AI settings, a cap saves itself after a pause ("Saving…", then a quiet "Saved") or says in Copper what failed,
// keeping what was typed. The Claude key the walk saves is taken out of the bench's key store at the end.
// Screenshots (1440×900): test-results/bench/shots, and as live-NN-<state>-<ar|en>.png in $QSONE_LIVE_SHOTS when it
// is set, with the paste → check → works video there as live-motion-paste-<ar|en>.webm.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import type { Locator, Page } from "@playwright/test";
import { texts } from "../src/i18n";
import { expect, test, type Walk } from "./bench";

const benchPort = Number(process.env.QSONE_BENCH_PORT || 1442);
const settingsFile = path.join(tmpdir(), benchPort === 1442 ? "qs-mind-one-bench" : `qs-mind-one-bench-${benchPort}`, "data", "settings.json");
const shotsDir = path.join("test-results", "bench", "shots");
const extra = process.env.QSONE_LIVE_SHOTS;

// Sample keys, not real ones: the bench takes a key with "-bench-ok-" in it, and refuses any other.
const REFUSED = "sk-ant-sample-not-a-real-key-refused-00000000000000";
const WORKS = "sk-ant-bench-ok-sample-not-a-real-key-000000000000000";

const ORDER = ["empty", "checking", "failed", "works", "saving", "saved", "save-failed"];
const say = (lang: "ar" | "en", key: keyof typeof texts) => texts[key][lang];

async function shot(page: Page, state: string, lang: string) {
  await page.waitForTimeout(450); // a line rises in over 200 ms ("Checking…" after 300 ms): the shot shows it settled
  const name = `live-${String(ORDER.indexOf(state) + 1).padStart(2, "0")}-${state}-${lang}.png`;
  mkdirSync(shotsDir, { recursive: true });
  const file = path.join(shotsDir, name);
  await page.screenshot({ path: file }); // the window, 1440×900
  if (extra) {
    mkdirSync(extra, { recursive: true });
    copyFileSync(file, path.join(extra, name));
  }
}

/** An expected refusal is not a problem of the walk: neither its HTTP status nor the browser's console line for it. */
function expected(walk: Walk, status: number, request: string) {
  for (const line of [`HTTP ${status} ${request}`, `status of ${status} `]) {
    const at = walk.problems.findIndex((problem) => problem.includes(line));
    if (at >= 0) walk.problems.splice(at, 1);
  }
}

/** The button is wholly inside the window as it is, with nothing scrolled to reach it. */
async function inView(page: Page, button: Locator, why: string) {
  const box = await button.boundingBox();
  const { width, height } = page.viewportSize()!;
  expect(box, why).not.toBeNull();
  expect(box!.x >= 0 && box!.y >= 0 && box!.x + box!.width <= width && box!.y + box!.height <= height, `${why}: ${JSON.stringify(box)} in ${width}×${height}`).toBe(true);
}

/** Pastes `text` into the focused field, as the engineer does: through the clipboard. */
async function paste(page: Page, text: string) {
  await page.evaluate((value) => navigator.clipboard.writeText(value), text);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("ControlOrMeta+v");
}

/** Connect AI alone, from the chat, as when the AI note was never agreed; agreed, with the API key chosen. */
async function openConnectAi(page: Page, lang: "ar" | "en") {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.addInitScript((value) => localStorage.setItem("qsone.language", value), lang); // the screen's language
  await page.request.put("/api/setup/language", { data: { state: "done", lang } });
  const saved = JSON.parse(readFileSync(settingsFile, "utf8")) as Record<string, unknown>;
  delete saved.ai_consent;
  writeFileSync(settingsFile, JSON.stringify(saved));
  await page.goto("/");
  await page.locator('[data-region="chat"]').getByRole("button", { name: say(lang, "connectAi"), exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: say(lang, "consentAgree"), exact: true }).click();
  await dialog.getByRole("button", { name: new RegExp(`^${say(lang, "aiLinkApiKey")}`) }).click();
  return dialog;
}

for (const lang of ["ar", "en"] as const) {
  test(`saves and checks as you go (${lang})`, async ({ walk, page }) => {
    walk.lang = lang;
    try {
      // Connect AI: a key checks itself as it is pasted --------------------------------------------------------
      const dialog = await openConnectAi(page, lang);
      const field = dialog.getByLabel(say(lang, "aiKeyLabel"));
      const next = dialog.getByRole("button", { name: say(lang, "setupNext"), exact: true });
      await expect(field).toBeEmpty();
      await expect(next).toBeDisabled();
      await expect(dialog.getByRole("button", { name: /^(Save|Check|حفظ|افحص|اتأكد)$/ })).toHaveCount(0);
      await shot(page, "empty", lang);
      const before = await next.boundingBox();

      await field.click();
      await paste(page, REFUSED);
      await expect(dialog.locator('[data-feedback="busy"]')).toBeVisible(); // at once: no pause for a paste
      await shot(page, "checking", lang);
      // what to do, in place: no "go to AI at the top" here, where there is no top bar
      const alert = dialog.getByRole("alert");
      await expect(alert).toContainText(lang === "ar" ? "رفض مفتاح Claude" : "refused this Claude key");
      await expect(alert).toContainText("console.anthropic.com");
      await expect(alert).not.toContainText(lang === "ar" ? "فوق" : "at the top");
      expected(walk, 409, "POST /api/settings/ai/check");
      await expect(field).toHaveValue(REFUSED); // kept, to be fixed
      await page.mouse.move(0, 0);
      await shot(page, "failed", lang);
      expect(await next.boundingBox(), "a two-line failure never moves Next").toEqual(before);
      await inView(page, next, "with a two-line failure, Next is on screen at 1440×900");
      // RF5: in a 380 px wide window, and at 200% zoom (a 1440×900 window is then 720×450 CSS px)
      for (const [width, height, where] of [[380, 900, "380 px wide"], [720, 450, "200% zoom"]] as const) {
        await page.setViewportSize({ width, height });
        await page.waitForTimeout(300);
        await inView(page, next, `with a two-line failure, Next is on screen ${where}`);
        await inView(page, dialog.getByRole("button", { name: say(lang, "setupSkip"), exact: true }), `Skip is on screen ${where}`);
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.waitForTimeout(300);

      await field.click();
      await paste(page, WORKS);
      await expect(dialog.getByText(say(lang, "aiLinkWorks"))).toBeVisible();
      await expect(next).toBeEnabled();
      expect(await next.boundingBox(), "Next never moved").toEqual(before);
      await shot(page, "works", lang);
      await next.click();
      await expect(page.getByRole("dialog")).toHaveCount(0);

      // AI settings: a cap saves itself after a pause ---------------------------------------------------------
      await page.locator('[data-region="topbar"]').getByRole("button", { name: say(lang, "more"), exact: true }).click();
      await page.getByRole("button", { name: say(lang, "ai"), exact: true }).click();
      const day = page.getByLabel(say(lang, "capDay"));
      await expect(day).not.toHaveValue("");
      const was = await day.inputValue();
      // the bench answers at once: held a moment here, so "Saving…" is seen
      await page.route("**/api/settings/ai/caps", async (route) => {
        if (route.request().method() === "PUT") await new Promise((resolve) => setTimeout(resolve, 1500));
        await route.continue();
      });
      await day.scrollIntoViewIfNeeded();
      await day.fill("16.00");
      const form = day.locator("xpath=ancestor::form");
      await expect(form.getByText(say(lang, "saving"))).toBeVisible();
      await shot(page, "saving", lang);
      await expect(form.getByText(say(lang, "saved"), { exact: true })).toBeVisible();
      await shot(page, "saved", lang);
      await page.unroute("**/api/settings/ai/caps");

      await day.fill("16,5");
      await day.press("Tab"); // leaving the field saves what it holds
      await expect(form.getByRole("alert")).toBeVisible();
      expected(walk, 422, "PUT /api/settings/ai/caps");
      await expect(day).toHaveValue("16,5");
      await expect(day).toHaveAttribute("aria-invalid", "true");
      await page.mouse.move(0, 0);
      await shot(page, "save-failed", lang);

      await day.fill(was); // as the bench had it
      await day.press("Tab");
      await expect(form.getByText(say(lang, "saved"), { exact: true })).toBeVisible();
      await expect(form.getByRole("alert")).toHaveCount(0);
    } finally {
      await page.request.post("/api/bench/forget-claude-key");
    }
  });
}

test("paste → check → works, on video", async ({ browser }) => {
  const dir = path.join("test-results", "bench", "video");
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir, size: { width: 1440, height: 900 } } });
  const page = await context.newPage();
  try {
    const dialog = await openConnectAi(page, "ar");
    await page.waitForTimeout(600);
    await dialog.getByLabel(say("ar", "aiKeyLabel")).click();
    await page.waitForTimeout(400);
    await paste(page, WORKS);
    await expect(dialog.getByText(say("ar", "aiLinkWorks"))).toBeVisible();
    await page.waitForTimeout(1200);
  } finally {
    await page.request.post("/api/bench/forget-claude-key");
    await context.close();
  }
  const file = path.join(dir, "live-motion-paste-ar.webm");
  await page.video()!.saveAs(file);
  if (extra) copyFileSync(file, path.join(extra, "live-motion-paste-ar.webm"));
});
