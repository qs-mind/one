// The live layer end to end (Plan 7 Task 5): agent cursors on the canvas, from the project's live events only.
// A cursor is // `data-testid="cursor-<agent id>"`, labelled with the role name in the page language, inside an aria-hidden wrapper.
import { expect, test, type Page } from "@playwright/test";
import { canvasReady, checker, estimator, frame, mockCore, small } from "./fixtures";

test.use({ viewport: { width: 1440, height: 900 } });

/** The team as the core lists it, with no one on a frame: what is on screen before any event. */
function quiet() {
  const scene = small();
  scene.team = { ...scene.team, agents: scene.team.agents.map((a) => ({ ...a, focus: null })) };
  return scene;
}

test("no event, no cursor", async ({ page }) => {
  await mockCore(page, quiet());
  await page.goto("/");
  await canvasReady(page);
  await expect(frame(page, "deliverable:pricing")).toBeVisible();
  await expect(page.locator('[data-testid^="cursor-"]')).toHaveCount(0);
});

test("an agent's cursor sits over its frame with its role name, hidden from screen readers", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await canvasReady(page);
  core.emit([{ type: "agent", agent: estimator }]);

  const cursor = page.getByTestId("cursor-est");
  await expect(cursor).toBeVisible();
  await expect(cursor).toContainText("مهندس التسعير - عينة");
  expect(await cursor.evaluate((el) => el.closest('[aria-hidden="true"]') !== null)).toBe(true);
  const c = (await cursor.boundingBox())!;
  const f = (await frame(page, "deliverable:pricing").boundingBox())!;
  // the arrow's point (the cursor's top-left corner) is on the frame: its body or its name strip
  expect(c.x).toBeGreaterThanOrEqual(f.x - 1);
  expect(c.x).toBeLessThanOrEqual(f.x + f.width + 1);
  expect(c.y).toBeGreaterThanOrEqual(f.y - 1);
  expect(c.y).toBeLessThanOrEqual(f.y + f.height + 1);
});

test("two cursors on one frame do not sit on top of each other", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await canvasReady(page);
  core.emit([
    { type: "agent", agent: estimator },
    { type: "agent", agent: checker },
  ]);
  await expect(page.getByTestId("cursor-est")).toBeVisible();
  await expect(page.getByTestId("cursor-chk")).toBeVisible();
  const a = (await page.getByTestId("cursor-est").boundingBox())!;
  const b = (await page.getByTestId("cursor-chk").boundingBox())!;
  expect(Math.abs(a.y - b.y) + Math.abs(a.x - b.x)).toBeGreaterThan(4); // 24 world px apart, at the fit-all zoom
});

test("a finished agent's cursor goes", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await canvasReady(page);
  core.emit([{ type: "agent", agent: estimator }]);
  await expect(page.getByTestId("cursor-est")).toBeVisible();
  core.emit([{ type: "agent", agent: { ...estimator, state: "done" } }]);
  await expect(page.getByTestId("cursor-est")).toHaveCount(0);
});

test("a cursor follows its agent to another frame", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await canvasReady(page);
  core.emit([{ type: "agent", agent: estimator }]);
  const cursor = page.getByTestId("cursor-est");
  await expect(cursor).toBeVisible();
  core.emit([{ type: "agent", agent: { ...estimator, focus: { frame: "deliverable:letter", anchor: null } } }]);
  const f = (await frame(page, "deliverable:letter").boundingBox())!;
  await expect
    .poll(async () => {
      const c = (await cursor.boundingBox())!;
      return c.x >= f.x - 1 && c.x <= f.x + f.width + 1 && c.y >= f.y - 1 && c.y <= f.y + f.height + 1;
    })
    .toBe(true);
});

/** Whether the frame's centre sits in the middle half of the canvas, where following puts it. */
async function centred(page: Page, key: "deliverable:pricing" | "deliverable:letter") {
  const f = (await frame(page, key).boundingBox())!;
  const c = (await page.locator('[data-region="canvas"]').boundingBox())!;
  const [fx, fy, cx, cy] = [f.x + f.width / 2, f.y + f.height / 2, c.x + c.width / 2, c.y + c.height / 2];
  return Math.abs(fx - cx) < c.width / 4 && Math.abs(fy - cy) < c.height / 4;
}

test("Follow keeps the agent's frame in view; a pan by hand stops it", async ({ page }) => {
  const core = await mockCore(page, quiet());
  await page.goto("/");
  await canvasReady(page);
  core.emit([{ type: "agent", agent: checker }]);
  await frame(page, "team:core").locator('li[data-agent="chk"]').getByRole("button", { name: /تابع/ }).click();
  const following = page.getByRole("banner").getByText("متابع مهندس المراجعة - عينة");
  await expect(following).toBeVisible();
  await expect.poll(() => centred(page, "deliverable:pricing")).toBe(true);

  core.emit([{ type: "agent", agent: { ...checker, focus: { frame: "deliverable:letter", anchor: null } } }]);
  await expect.poll(() => centred(page, "deliverable:letter")).toBe(true);

  await page.waitForTimeout(400); // a pan within 100 ms of a follow move is the camera's own, not the engineer's
  await page.mouse.move(900, 400);
  await page.mouse.wheel(0, 300);
  await expect(following).toBeHidden();
});
