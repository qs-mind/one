// The truth guards on the real app and core, with the bench's scripted weak model (the tender day's
// gemini-3.1-flash-lite): it writes a letter dated tomorrow with a blank for its total, then claims every item priced,
// the Deliverable ready and work under way. The letter is refused, the claim goes back once (the chat drops it), and
// the facts from ONE's records stand beside the answer, still there after a reload.
import { expect, test } from "./bench";

test("a weak model's claims: sent back once, and the records' facts beside the answer", async ({ walk, page }) => {
  await walk.start("ar");
  await walk.createProject("صدق الرد - عينة");
  await walk.addFiles();
  await walk.brief("bench:weak سعّر المقايسة كلها واكتب الخطاب");
  const facts = page.locator("[data-facts]").last();
  // Imported client rates are not pricing done by ONE (d13f801).
  const coverage = "من سجلات ONE: 4 بنود، فيهم 4 بسعر العميل · ONE سعّر 0 · مفيش مخرج لسه";
  await expect(facts).toBeVisible();
  await expect(facts).toContainText(coverage);
  await expect(facts.getByRole("status").filter({ hasText: "مفيش حاجة شغالة دلوقتي" })).toBeVisible();
  await expect(page.getByText(/تم الانتهاء من تسعير/)).toHaveCount(1); // the answer sent back is not shown
  await walk.shot("truth-facts");
  await page.reload();
  await expect(page.locator("[data-facts]").last()).toContainText(coverage);
});
