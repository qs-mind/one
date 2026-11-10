// First launch, walked as the engineer does it: the language, who they are, then AI later, and Home. Someone
// upgrading sees step 2 only, and its Next ends at Home. The address always follows the step.
import { engineer } from "../src/texts/engineer";
import { firstlaunch } from "../src/texts/firstlaunch";
import { open, shot, test, expect, type Lang } from "./app";

const profile = [engineer.first_name, engineer.last_name, engineer.position, engineer.company];

for (const lang of ["ar", "en"] as Lang[]) {
  test(`a clean start walks the three steps to Home (${lang})`, async ({ page }, info) => {
    await open(page, "/", { lang, first: "" });
    await expect(page).toHaveURL(/#\/welcome\/language$/);
    await expect(page.getByRole("heading", { level: 1, name: firstlaunch.languageTitle[lang] })).toBeVisible();
    await page.getByRole("button", { name: firstlaunch.next[lang] }).click();

    await expect(page).toHaveURL(/#\/welcome\/profile$/);
    await expect(page.getByRole("heading", { level: 1, name: firstlaunch.whoTitle[lang] })).toBeVisible();
    for (const pair of profile) await page.getByRole("textbox", { name: pair[lang] }).fill(lang === "ar" ? "مهندس - عينة" : "Sample");
    await shot(page, info, `welcome-profile-${lang}`);
    await page.getByRole("button", { name: firstlaunch.next[lang] }).click();

    await expect(page).toHaveURL(/#\/welcome\/ai$/);
    await expect(page.getByRole("heading", { level: 1, name: firstlaunch.aiTitle[lang] })).toBeVisible();
    await shot(page, info, `welcome-ai-${lang}`);
    await page.getByRole("button", { name: firstlaunch.later[lang] }).click();

    await expect(page.locator('[data-place="home"]')).toBeVisible();
    await expect(page).toHaveURL(/#\/$/);
  });
}

test("someone upgrading is pinned to step 2, and its Next ends at Home", async ({ page }) => {
  await open(page, "/welcome/ai", { lang: "en", first: "upgrade" });
  await expect(page).toHaveURL(/#\/welcome\/profile$/);
  await expect(page.getByRole("button", { name: firstlaunch.back.en })).toHaveCount(0);
  for (const pair of profile) await page.getByRole("textbox", { name: pair.en }).fill("Sample");
  await page.getByRole("button", { name: firstlaunch.next.en }).click();
  await expect(page.locator('[data-place="home"]')).toBeVisible();
});

test("a place's address in first launch leads to the step still to do", async ({ page }) => {
  await open(page, "/settings/look", { lang: "ar", first: "profile" });
  await expect(page).toHaveURL(/#\/welcome\/profile$/);
});
