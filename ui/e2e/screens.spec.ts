// Screenshots of the key screens, in Arabic and English, at 1440, 1024 and 800 px. Chromium only. Every run keeps
// them under test-results/ (ignored by git) for a look by eye. They are compared with committed baselines only on the
// Ubuntu CI runner, their one reference; the baselines are made there by the workflow_dispatch run with
// --update-snapshots, downloaded with `gh run download` and committed. Until a baseline exists the run notes it and
// passes, so CI stays green before the first baselines are in.
import { existsSync } from "node:fs";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { mockCore, small, workspaceReady } from "./fixtures";

test.skip(({ browserName }) => browserName !== "chromium", "screenshots are taken on Chromium only (their reference)");

const reference = !!process.env.CI && process.platform === "linux";

async function shot(page: Page, name: string, info: TestInfo) {
  const file = `${name}.png`;
  await page.screenshot({ path: info.outputPath(file), animations: "disabled", caret: "hide" });
  if (!reference) return;
  const updating = info.config.updateSnapshots === "all" || info.config.updateSnapshots === "changed";
  if (updating || existsSync(info.snapshotPath(file, { kind: "screenshot" }))) {
    await expect(page).toHaveScreenshot(file, { animations: "disabled", caret: "hide" });
  } else {
    info.annotations.push({ type: "no baseline", description: `${file}: run the e2e workflow with update-snapshots` });
  }
}

const sizes = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 800, height: 900 },
];

for (const language of ["ar", "en"] as const) {
  for (const size of sizes) {
    test(`workspace-${language}-${size.width}`, async ({ page }, info) => {
      await page.setViewportSize(size);
      await mockCore(page, small(), { language });
      await page.goto("/");
      await workspaceReady(page, page.getByRole("grid"));
      await expect(page.getByRole("grid")).toContainText("03/01"); // the priced BOQ's rows came
      await shot(page, `workspace-${language}-${size.width}`, info);
    });
  }

  test(`general-chat-${language}`, async ({ page }, info) => {
    await page.setViewportSize(sizes[0]!);
    await mockCore(page, small(), { language, remembered: false });
    await page.goto("/");
    const box = page.locator("[data-command-box]");
    await box.fill(language === "ar" ? "إيه آخر أخبار مناقصة البرج؟ - عينة" : "What is new on the tower tender? (sample)");
    await box.press("Enter");
    await expect(page.getByRole("log")).toContainText(language === "ar" ? "رد عينة" : "sample reply");
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    await shot(page, `general-chat-${language}`, info);
  });

  test(`palette-${language}`, async ({ page }, info) => {
    await page.setViewportSize(sizes[0]!);
    await mockCore(page, small(), { language });
    await page.goto("/");
    await workspaceReady(page);
    await page.getByRole("button", { name: language === "ar" ? "بحث Ctrl K" : "Search Ctrl K" }).click();
    await expect(page.getByRole("dialog", { name: language === "ar" ? "بحث وأوامر" : "Search and commands" })).toBeVisible();
    await shot(page, `palette-${language}`, info);
  });
}
