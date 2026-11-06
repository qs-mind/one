// The bench walks: each drives the real app (real core, real Records files) with the fake AI of core/tests/bench.
// The Brief's keyword picks the fake's scenario: bench:chat, bench:question, bench:boq, bench:deliverable,
// bench:team; none is the full tender walk-through. Run: npm run test:bench.
import { expect, test } from "./bench";

test("full tender walk-through, in Arabic", async ({ walk }) => {
  await walk.start("ar");
  await walk.shot("app-open");
  await walk.createProject("مشروع عينة - منصة الاختبار");
  await walk.shot("project-created");
  await walk.addFiles();
  await walk.shot("files-added");
  const kinds = await walk.brief("سعّر جدول الكميات المرفق وجهّز العطاء");
  expect.soft(kinds, "the cards of the walk-through, in order").toEqual(["rows", "question", "approval", "rows"]);
  // the Brief's steps fold into its work log line when it ends; open it to read them
  await walk.chat.getByRole("button", { name: /^اشتغل|^Worked for/ }).last().click();
  await expect.soft(walk.chat.getByText(/مهندس المراجعة|Checking QS/).first(), "the Checking QS's review is in the chat").toBeVisible();
  await walk.deliverables(2);
});

test("BOQ import, in English", async ({ walk }) => {
  await walk.start("en");
  await walk.createProject("Sample project - test bench");
  await walk.addFiles();
  const kinds = await walk.brief("bench:boq Import the attached BOQ");
  expect.soft(kinds).toEqual(["rows"]);
  await walk.clientBoq("حفر في تربة عادية لأي عمق (عينة)");
});

test("Deliverables from a BOQ, in English", async ({ walk }) => {
  await walk.start("en");
  await walk.createProject("Sample deliverables - test bench");
  await walk.addFiles();
  await walk.brief("bench:deliverable Make the priced BOQ and the cover letter");
  await walk.deliverables(2);
  await walk.notInClientFlag(); // the fake prices one row of its own: the Checking QS flags it
});

test("a view of sourced numbers, in Arabic (decision 16.1)", async ({ walk }) => {
  await walk.start("ar");
  await walk.createProject("عرض عينة - منصة الاختبار");
  await walk.addFiles();
  await walk.brief("bench:view اعرض أرقام أول بند");
  const view = walk.chat.getByRole("region", { name: "نظرة على المقايسة (عينة تجريبية)" });
  await expect.soft(view, "the view is in the chat").toBeVisible();
  await expect.soft(view, "an Arabic view reads right to left").toHaveAttribute("dir", "rtl");
  await expect.soft(view.getByText("بيانات تجريبية"), "the view is labelled sample data").toBeVisible();
  await walk.shot("view");
  // Wide views open at the document's width (62e56f4), with the same sourced blocks.
  await view.getByRole("button", { name: "افتح كمستند", exact: true }).click();
  const documentView = walk.document.getByRole("region", { name: "نظرة على المقايسة (عينة تجريبية)" });
  await expect(documentView).toBeVisible();
  await expect(documentView).toHaveAttribute("dir", "rtl");
  await expect(documentView.getByText("بيانات تجريبية")).toBeVisible();
  await expect(documentView.getByRole("table")).toBeVisible();
  await documentView.getByRole("button", { name: /جاي منين/ }).first().click();
  const source = walk.page.getByRole("dialog", { name: "المصدر" });
  await expect.soft(source, "a number opens its source").toBeVisible();
  await expect(source).toContainText("جدول كميات - عينة اختبار (sample BOQ).xlsx");
  await walk.shot("view-source");
});

test("a question card, in English", async ({ walk }) => {
  await walk.start("en");
  await walk.createProject("Sample question - test bench");
  const kinds = await walk.brief("bench:question What do you need from me?");
  expect.soft(kinds).toEqual(["question"]);
});

test("plain replies in the General chat and a project, in Arabic", async ({ walk }) => {
  await walk.start("ar");
  await walk.brief("bench:chat أهلا");
  await walk.createProject("مشروع عينة للشات - منصة الاختبار");
  await walk.brief("bench:chat عامل إيه؟");
  await walk.page.reload();
  await expect.soft(walk.chat.getByText("عامل إيه؟"), "the project chat is kept after a reload").toBeVisible();
  await walk.shot("chat-after-reload");
});

test("the message box's model and effort reach the Lead QS, in English", async ({ walk }) => {
  await walk.start("en");
  await walk.createProject("Sample model and effort - test bench"); // a project's Lead QS
  const page = walk.page;
  const box = page.getByRole("textbox", { name: walk.w.message });
  await box.click();
  // the card lists every bench model; the specialist one takes an effort with no known default
  await page.getByRole("button", { name: "Model: Bench lead (fake AI). Choose another" }).click();
  await page.getByRole("menuitemradio", { name: "Bench specialist (fake AI)" }).click();
  await page.getByRole("button", { name: "Effort: Auto (the model's own). Click for Low" }).click();
  await page.getByRole("button", { name: "Effort: Low. Click for Medium" }).click();
  await walk.shot("model-and-effort-picked");
  await walk.brief("bench:chat Which model?");
  await expect.soft(walk.chat.getByText(/Model: bench-specialist\. Effort: medium\./)).toBeVisible();
  // remembered by the core, also after a reload
  await page.reload();
  await box.click();
  await expect.soft(page.getByRole("button", { name: "Effort: Medium. Click for High" })).toBeVisible();
  await page.getByRole("button", { name: "Model: Bench specialist (fake AI). Choose another" }).click();
  await page.getByRole("menuitemradio", { name: "Bench checker (fake AI)" }).click();
  await expect.soft(page.getByRole("button", { name: /^Effort:/ }), "a model with no effort shows none").toHaveCount(0);
});
