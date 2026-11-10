// Every place of the interface opens from its address, in Arabic and English, light and dark: the right place, the
// page's language and direction, the rail beside it (none in first launch) with only the place scrolling, and nothing
// wider than the window, on a desktop and on a phone.
import { common } from "../src/texts/common";
import { open, noSidewaysScroll, shot, test, expect, TENDER, windowStill, type Lang, type Theme } from "./app";

const places: { name: string; address: string; place: string; first?: "" }[] = [
  { name: "home", address: "/", place: "home" },
  { name: "tender", address: `/tender/${TENDER}`, place: "tender" },
  { name: "room", address: `/tender/${TENDER}/room`, place: "room" },
  { name: "member", address: `/tender/${TENDER}/member/lead-qs`, place: "member" },
  ...["me", "ai", "team", "caps", "connectors", "backup", "privacy", "look"].map((section) => ({
    name: `settings-${section}`,
    address: `/settings/${section}`,
    place: "settings",
  })),
  { name: "welcome-language", address: "/welcome/language", place: "welcome", first: "" as const },
];

for (const lang of ["ar", "en"] as Lang[])
  for (const theme of ["light", "dark"] as Theme[])
    for (const { name, address, place, first } of places)
      test(`${name} (${lang}, ${theme})`, async ({ page }, info) => {
        await open(page, address, { lang, theme, first });
        await expect(page.locator(`[data-place="${place}"]`)).toBeVisible();
        const html = page.locator("html");
        await expect(html).toHaveAttribute("lang", lang);
        await expect(html).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");
        await expect(html).toHaveAttribute("data-theme", theme);
        const rail = page.getByRole("navigation", { name: common.navigation[lang] });
        if (place === "welcome") await expect(rail).toHaveCount(0);
        else await expect(rail).toBeVisible();
        await page.waitForTimeout(300); // the place's first motion
        await noSidewaysScroll(page);
        if (place !== "welcome") await windowStill(page);
        await shot(page, info, `${name}-${lang}-${theme}`);
        await page.setViewportSize({ width: 380, height: 800 });
        await noSidewaysScroll(page);
        await shot(page, info, `${name}-${lang}-${theme}-phone`);
      });

test("the rail goes between Home, the tenders and Settings", async ({ page }) => {
  await open(page, "/", { lang: "en" });
  const rail = page.getByRole("navigation", { name: common.navigation.en });
  await rail.getByRole("link", { name: common.settings.en }).click();
  await expect(page.locator('[data-place="settings"]')).toHaveAttribute("data-section", "me");
  await rail.getByRole("link", { name: common.home.en }).click();
  await expect(page.locator('[data-place="home"]')).toBeVisible();
});
