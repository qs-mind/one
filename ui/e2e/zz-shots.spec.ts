// Before/after screenshots for the founder (not committed). SHOTS_DIR, SHOTS_TAG from the environment.
import { expect, test, type Page } from "@playwright/test";
import { canvasReady, frame, mockCore, small } from "./fixtures";

const dir = process.env.SHOTS_DIR!;
const tag = process.env.SHOTS_TAG!;
const file = (n: string, name: string) => `${dir}/ui-${n}-${name}-${tag}.png`;

const agent = { en: "Lead QS", ar: "كبير مهندسي الكميات" };
const progress = (id: string, en: string, ar: string) => ({ type: "data-progress", id, data: { agent, text: { en, ar }, lang: "ar" } });
const columns = [
  { key: "description", label: { en: "Item", ar: "البند" } },
  { key: "unit", label: { en: "Unit", ar: "الوحدة" } },
  { key: "rate", label: { en: "Rate", ar: "السعر" } },
  { key: "currency", label: { en: "Currency", ar: "العملة" } },
  { key: "vat", label: { en: "VAT", ar: "الضريبة" } },
];
const rows = [
  { description: "بالمتر المكعب خرسانة مسلحة للأعمدة والكمرات طبقاً للمواصفات والرسومات - عينة", unit: "م3", rate: "4150.00", currency: "EGP", vat: "14%" },
  { description: "بالطن حديد تسليح عالي المقاومة - عينة", unit: "طن", rate: "38500.00", currency: "EGP", vat: "14%" },
  { description: "بالمتر المربع بلاط بورسلين 60×60 - عينة", unit: "م2", rate: "620.00", currency: "EGP", vat: "14%" },
];
const card = (id: string, status: string, extra: object = {}) => ({
  type: "data-card",
  id,
  data: {
    kind: "rows",
    title: { en: "Keep these prices?", ar: "احفظ الأسعار دي؟" },
    detail: { en: "Tick the rows to keep (sample data).", ar: "علّم على الصفوف اللي تتحفظ - عينة." },
    options: ["keep", "no"],
    status,
    payload: { columns, rows, tick: true },
    ...extra,
  },
});
const reply =
  "راجعت ملف boq-priced.xls: 100 بند، والخلية H18 فيها السعر الإجمالي.\n\n" +
  "- البند الأول في Project Records\n- الكمية 250 م3 من Sheet1\n\n" +
  "I checked the file نموذج المقايسة.xlsx and it has 3 sheets.";

function messages(cards: object[]) {
  return [
    { id: "u1", role: "user", parts: [{ type: "text", text: "راجع الـ BOQ وسعّر بنود الخرسانة - عينة\nthe file is boq-priced.xls" }] },
    {
      id: "a1",
      role: "assistant",
      parts: [progress("p1", "Reading the BOQ", "يقرا المقايسة"), progress("p2", "Pricing the concrete items", "يسعّر بنود الخرسانة"), { type: "text", text: reply }, ...cards],
    },
  ];
}

async function open(page: Page, language: "ar" | "en", body: object[], width = 1440, frames?: [] | undefined) {
  await page.setViewportSize({ width, height: 900 });
  const scene = small();
  scene.project.name = language === "ar" ? "برج إداري بالعاصمة الإدارية الجديدة - عينة" : "Administrative tower, New Capital (sample)";
  if (frames) scene.layout.frames = frames;
  await mockCore(page, scene, { language });
  await page.route(`**/api/chat/${scene.project.id}/messages`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ messages: body }) }),
  );
  await page.goto("/");
  await canvasReady(page);
  await page.waitForTimeout(800);
}

const chat = (page: Page) => page.locator('aside[data-region="chat"]');

test("01 chat direction, Arabic", async ({ page }) => {
  await open(page, "ar", messages([]));
  await chat(page).getByRole("log").evaluate((el) => (el.scrollTop = 0));
  await chat(page).screenshot({ path: file("01", "chat-direction-ar") });
});

test("02 progress in the Brief's language, English screen", async ({ page }) => {
  await open(page, "en", messages([]));
  await chat(page).getByRole("log").evaluate((el) => (el.scrollTop = 0));
  await chat(page).screenshot({ path: file("02", "progress-brief-language-en-ui") });
});

test("03 price rows card in the chat", async ({ page }) => {
  await open(page, "ar", messages([card("c1", "pending")]));
  await page.getByText("احفظ الأسعار دي؟").last().scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => undefined);
  await chat(page).screenshot({ path: file("03", "rows-card-ar") });
});

test("04 answered card then a new one", async ({ page }) => {
  await open(page, "ar", messages([card("c0", "settled", { choice: "keep", rows_ok: [0, 1, 2] }), card("c1", "pending")]));
  await chat(page).screenshot({ path: file("04", "answered-card-folds-ar") });
});

for (const language of ["en", "ar"] as const) {
  test(`05 first open fit, ${language}`, async ({ page }) => {
    await open(page, language, [], 1440, []);
    await page.screenshot({ path: file("05", `canvas-fit-${language}`) });
  });
}

test("06 the message box, chat open and folded", async ({ page }) => {
  await open(page, "en", messages([]));
  await page.screenshot({ path: file("06", "message-box-chat-open-en") });
  await page.getByRole("button", { name: /close the chat|fold/i }).first().click().catch(() => undefined);
  await page.waitForTimeout(400);
  await page.screenshot({ path: file("06", "message-box-chat-folded-en") });
});

for (const [language, width] of [["ar", 1440], ["en", 940], ["ar", 1024]] as const) {
  test(`07 top bar ${language} ${width}`, async ({ page }) => {
    await open(page, language, [], width);
    await page.locator('[data-region="topbar"]').screenshot({ path: file("07", `top-bar-${language}-${width}`) });
    await page.screenshot({ path: file("08", `placeholder-${language}-${width}`), clip: { x: 0, y: 900 - 220, width, height: 220 } });
  });
}

for (const language of ["ar", "en"] as const) {
  test(`09 a newly opened frame, ${language}`, async ({ page }) => {
    await open(page, language, []);
    // the founder's case: open a file from the Project files frame
    const files = frame(page, "files:all");
    await files.locator("header h3").click();
    await page.keyboard.press("Enter").catch(() => undefined);
    await page.waitForTimeout(600);
    const button = files.getByRole("button", { name: /مقايسة العميل/ });
    if (await button.count()) await button.click();
    await expect(frame(page, "file:boq")).toHaveCount(1);
    await page.waitForTimeout(900);
    await page.screenshot({ path: file("09", `new-frame-${language}`) });
  });
}
