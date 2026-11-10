// The engineer's first walk on the real app and core: first launch (step 2, who they are), saved by the core, then
// Home, and every Settings section, where the profile they typed is shown back. A reload keeps them out of first
// launch: the core has their profile.
import { common } from "../src/texts/common";
import { engineer } from "../src/texts/engineer";
import { firstlaunch } from "../src/texts/firstlaunch";
import { expect, test } from "./bench";

const SECTIONS = ["me", "ai", "team", "caps", "connectors", "backup", "privacy", "look"];

test("first launch, then Home and every Settings section", async ({ walk, page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/welcome\/profile$/);
  await expect(page.getByRole("heading", { level: 1, name: firstlaunch.whoTitle.ar })).toBeVisible();
  const typed: [{ ar: string }, string][] = [
    [engineer.first_name, "مهندس"],
    [engineer.last_name, "عينة"],
    [engineer.position, "مهندس تسعير - عينة"],
    [engineer.company, "شركة عينة"],
  ];
  for (const [label, value] of typed) await page.getByRole("textbox", { name: label.ar }).fill(value);
  const chosen: [{ ar: string }, { ar: string }][] = [
    [engineer.org_type, engineer.contractor],
    [engineer.country, engineer.EG],
  ];
  for (const [label, choice] of chosen) {
    await page.getByRole("combobox", { name: label.ar }).click();
    await page.getByRole("option", { name: choice.ar }).click();
  }
  await walk.shot("welcome-profile");
  await page.getByRole("button", { name: firstlaunch.next.ar }).click();

  await expect(walk.place("home")).toBeVisible();
  await expect(page).toHaveURL(/#\/$/);
  await walk.shot("home");
  const profile = (await (await page.request.get("/api/engineer/profile")).json()) as { complete: boolean; first_name: string };
  expect(profile).toMatchObject({ complete: true, first_name: "مهندس" });

  const rail = page.getByRole("navigation", { name: common.navigation.ar });
  await rail.getByRole("link", { name: common.settings.ar }).click();
  await expect(walk.place("settings")).toHaveAttribute("data-section", "me");
  await expect(page.getByRole("textbox", { name: engineer.first_name.ar })).toHaveValue("مهندس");
  for (const section of SECTIONS) {
    await page.goto(`/#/settings/${section}`);
    await expect(walk.place("settings")).toHaveAttribute("data-section", section);
    await page.waitForTimeout(500); // what the section reads from the core
    await walk.shot(`settings-${section}`);
  }

  await page.goto("/");
  await page.reload();
  await expect(walk.place("home")).toBeVisible();
});
