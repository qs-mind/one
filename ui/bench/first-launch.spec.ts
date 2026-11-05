// The first launch, on the real app and core, as on a fresh data folder: the bench's seed passes the first launch for
// the other walks, so this walk first takes its answers out of settings.json (steps, consent, Usage Stats, language).
// It ends where the other walks start: every step passed and the AI note agreed. It never presses a link that opens a
// browser, and never looks for Claude Code (the bench's guard keeps both off anyway).
// Screenshots: test-results/bench/shots, and as setup-NN-<step>-<ar|en>.png in $QSONE_SETUP_SHOTS when it is set.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import type { Page } from "@playwright/test";
import { expect, test, type Walk } from "./bench";

const benchPort = Number(process.env.QSONE_BENCH_PORT || 1442);
const settingsFile = path.join(tmpdir(), benchPort === 1442 ? "qs-mind-one-bench" : `qs-mind-one-bench-${benchPort}`, "data", "settings.json");
const FIRST_LAUNCH = ["setup", "setup_done_at", "ai_consent", "usage_stats", "language"];

/** settings.json without the first launch's answers; the core reads the file on every call. */
function forgetFirstLaunch(keys = FIRST_LAUNCH) {
  const saved = JSON.parse(readFileSync(settingsFile, "utf8")) as Record<string, unknown>;
  for (const key of keys) delete saved[key];
  writeFileSync(settingsFile, JSON.stringify(saved));
}

/** Each step's main button is wholly in the window as it opens, with nothing scrolled: the bar stays at its foot. */
async function barInView(page: Page, name: string, why: string) {
  const box = await page.getByRole("button", { name, exact: true }).boundingBox();
  const { width, height } = page.viewportSize()!;
  expect(box, why).not.toBeNull();
  expect(box!.x >= 0 && box!.y >= 0 && box!.x + box!.width <= width && box!.y + box!.height <= height, `${why}: ${JSON.stringify(box)} in ${width}×${height}`).toBe(true);
}

const ORDER = ["language", "account", "ai-consent", "ai-choice", "card", "usage", "ready", "app", "chat-consent", "connect-ai-alone"];
async function shot(walk: Walk, step: string) {
  const file = await walk.shot(`${step}-${walk.lang}`);
  const extra = process.env.QSONE_SETUP_SHOTS;
  if (extra) {
    mkdirSync(extra, { recursive: true });
    const n = String(ORDER.indexOf(step) + 1).padStart(2, "0");
    copyFileSync(file, path.join(extra, `setup-${n}-${step}-${walk.lang}.png`));
  }
}

const words = {
  ar: {
    language: "اختار لغتك",
    pick: "العربية",
    account: "حساب QS Mind بتاعك",
    connect: "وصّل الذكاء الاصطناعي",
    agree: "فهمت",
    apiKey: /^مفتاح API/,
    card: "بطاقة التعريف",
    role: "مهندس كميات عند مقاول",
    country: "البلد",
    countryName: "مصر",
    city: "المدينة",
    cityName: "القاهرة",
    usage: "إحصائيات الاستخدام",
    dontShare: "ماتشاركش",
    ready: "ONE جاهز",
    next: "التالي",
    skip: "تخطّى",
    start: "ابدأ من غير فولدر", // the Ready screen offers a tender folder first
    message: "رسالة إلى كبير مهندسي الكميات",
  },
  en: {
    language: "Choose your language",
    pick: "English",
    account: "Your QS Mind account",
    connect: "Connect AI",
    agree: "I understand",
    apiKey: /^An API key/,
    card: "Introduction card",
    role: "QS at a consultant",
    country: "Country",
    countryName: "Saudi Arabia",
    city: "City",
    cityName: "Riyadh",
    usage: "Usage Stats",
    dontShare: "Don't share",
    ready: "ONE is ready",
    next: "Next",
    skip: "Skip",
    start: "Start without a folder",
    message: "Message to the Lead QS",
  },
} as const;

for (const lang of ["ar", "en"] as const) {
  test(`first launch from a fresh data folder, in ${lang === "ar" ? "Arabic" : "English"}`, async ({ walk, page }) => {
    const w = words[lang];
    forgetFirstLaunch();
    await page.goto("/");
    const title = (name: string) => page.getByRole("heading", { level: 1, name });
    await expect(title(words.ar.language).or(title(words.en.language))).toBeVisible();
    walk.lang = lang;

    await page.getByRole("button", { name: w.pick, exact: true }).click();
    await expect(title(w.language)).toBeVisible();
    await shot(walk, "language");
    await barInView(page, w.next, "Next on the language step");
    await page.getByRole("button", { name: w.next, exact: true }).click();

    await expect(title(w.account)).toBeVisible();
    await shot(walk, "account");
    await barInView(page, w.skip, "Skip on the account step");
    const bar = page.locator("[data-step-bar]");
    const barAt = await bar.boundingBox();
    await page.getByRole("button", { name: w.skip, exact: true }).click();

    await expect(title(w.connect)).toBeVisible();
    // the next step slides in; its bar does not: it is where it was, from the first frame
    expect(await bar.boundingBox(), "the bar stays still as the step changes").toEqual(barAt);
    await shot(walk, "ai-consent");
    await page.getByRole("button", { name: w.agree, exact: true }).click();
    await page.getByRole("button", { name: w.apiKey }).click();
    await shot(walk, "ai-choice");
    await barInView(page, w.next, "Next on Connect AI");
    // no Save or Check: Next waits in its place until a key works (live.spec.ts checks keys)
    await expect(page.getByRole("button", { name: w.next, exact: true })).toBeDisabled();
    await page.getByRole("button", { name: w.skip, exact: true }).click(); // the bench has its own AI link already

    await expect(title(w.card)).toBeVisible();
    await page.getByRole("radio", { name: w.role }).click();
    await page.getByLabel(w.country).selectOption({ label: w.countryName });
    await page.getByLabel(w.city).fill(w.cityName);
    await expect(page.getByLabel(w.country).locator("option")).toHaveCount(4); // no blank choice
    await expect(page.locator("input[maxlength='3']")).toHaveCount(0); // the country says the currency
    await shot(walk, "card");
    await barInView(page, w.next, "Next on the card step");
    // the flow fits a 380 px wide window: nothing scrolls sideways
    const size = page.viewportSize()!;
    await page.setViewportSize({ width: 380, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(380);
    await walk.shot(`card-380-${lang}`);
    await barInView(page, w.next, "Next on the card step, 380 px wide");
    await page.setViewportSize(size);
    await page.getByRole("button", { name: w.next, exact: true }).click();

    await expect(title(w.usage)).toBeVisible();
    await shot(walk, "usage");
    await barInView(page, w.dontShare, "Don't share on Usage Stats");
    await page.getByRole("button", { name: w.dontShare, exact: true }).click();

    await expect(title(w.ready)).toBeVisible();
    await shot(walk, "ready");
    await barInView(page, w.start, "Start on Ready");
    await page.getByRole("button", { name: w.start, exact: true }).click();
    await expect(page.getByRole("textbox", { name: w.message })).toBeVisible();
    await shot(walk, "app");

    const setup = (await (await page.request.get("/api/setup")).json()) as { done: boolean; steps: Record<string, string> };
    expect(setup).toEqual({ done: true, steps: { language: "done", account: "skipped", ai: "skipped", card: "done", usage: "done" } });
    expect(((await (await page.request.get("/api/settings/ai-consent")).json()) as { at: string | null }).at).toBeTruthy();
    expect(await (await page.request.get("/api/engineer/card")).json()).toMatchObject({ city: w.cityName, currency: lang === "ar" ? "EGP" : "SAR" });
    expect(await (await page.request.get("/api/settings/usage-stats")).json()).toEqual({ on: false });

    // Without the AI note agreed, the chat leads to Connect AI alone, and back.
    forgetFirstLaunch(["ai_consent"]);
    await page.reload();
    const connect = page.locator('[data-region="chat"]').getByRole("button", { name: w.connect, exact: true });
    await expect(connect).toBeVisible();
    await shot(walk, "chat-consent");
    await connect.click();
    await expect(page.getByRole("dialog").getByRole("heading", { level: 1, name: w.connect })).toBeVisible();
    await shot(walk, "connect-ai-alone");
    await page.getByRole("button", { name: w.agree, exact: true }).click();
    await page.getByRole("button", { name: w.skip, exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(connect).toHaveCount(0);
  });
}
