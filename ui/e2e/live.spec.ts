// The live layer end to end (spec "Agents at work"), from the project's live events only: no cursors; an agent
// working on the open document puts a thin Slate line at the start edge of its row (`[data-working-line]`), with the
// role's name on hover (its title) and hidden from screen readers; one on another document puts a dot by that
// document in the switcher.
import { expect, test } from "@playwright/test";
import { checker, estimator, mockCore, small, switcher, workspaceReady } from "./fixtures";

test.use({ viewport: { width: 1440, height: 900 } });

/** The team as the core lists it, with no one on a document: what is on screen before any event. */
function quiet() {
  const scene = small();
  scene.team = { ...scene.team, agents: scene.team.agents.map((a) => ({ ...a, focus: null })) };
  return scene;
}

const line = '[data-working-line]';

test("no event, no line and no cursor", async ({ page }) => {
  await mockCore(page, quiet());
  await page.goto("/");
  await workspaceReady(page, page.getByRole("grid"));
  await expect(page.locator(line)).toHaveCount(0);
  await expect(page.locator('[data-testid^="cursor-"]')).toHaveCount(0);
});

test("an agent's row gets a thin line at its start edge, its role on hover, hidden from screen readers", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  const grid = page.getByRole("grid");
  await workspaceReady(page, grid);
  core.emit([{ type: "agent", agent: estimator }]); // on row r2: item 03/03

  const mark = page.locator(line);
  await expect(mark).toHaveCount(1);
  await expect(mark).toHaveAttribute("title", "مهندس التسعير - عينة");
  expect(await mark.evaluate((el) => el.closest('[aria-hidden="true"]') !== null)).toBe(true);
  const m = (await mark.boundingBox())!;
  const row = (await grid.getByRole("row").filter({ hasText: "03/03" }).boundingBox())!;
  expect(Math.abs(m.y - row.y)).toBeLessThanOrEqual(2);
  // at the row's start edge: the right in Arabic
  const sheet = (await page.locator("[data-document-sheet]").boundingBox())!;
  expect(sheet.x + sheet.width - (m.x + m.width)).toBeLessThan(16);
});

test("two agents on two rows: two lines", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await workspaceReady(page, page.getByRole("grid"));
  core.emit([
    { type: "agent", agent: estimator },
    { type: "agent", agent: checker },
  ]);
  await expect(page.locator(line)).toHaveCount(2);
});

test("a finished agent's line goes", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await workspaceReady(page, page.getByRole("grid"));
  core.emit([{ type: "agent", agent: estimator }]);
  await expect(page.locator(line)).toHaveCount(1);
  core.emit([{ type: "agent", agent: { ...estimator, state: "done" } }]);
  await expect(page.locator(line)).toHaveCount(0);
});

test("an agent on another document: no line here, a dot by that document in the switcher", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await workspaceReady(page, page.getByRole("grid"));
  core.emit([{ type: "agent", agent: { ...estimator, focus: { frame: "deliverable:letter", anchor: null } } }]);
  await switcher(page).click();
  const letter = page.getByRole("menu").getByRole("menuitem", { name: /خطاب العطاء - مسودة عينة/ });
  await expect(letter.locator("[data-working-dot]")).toHaveCount(1);
  await expect(page.getByRole("menu").getByRole("menuitem", { name: /تسعير المقايسة - عينة/ }).locator("[data-working-dot]")).toHaveCount(0);
  await expect(page.locator(line)).toHaveCount(0);
});
