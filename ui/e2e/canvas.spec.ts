// The Project Canvas end to end, on Chromium and WebKit (the closest free stand-in for WebKitGTK), against the built
// screen with every /api call answered by the fixtures. What the plan's review focus asks: the chrome mirrors in
// Arabic, the layout comes back from the core after a reload, the keyboard reaches everything, shortcuts go by
// KeyboardEvent.code, Arabic titles fit their strips, and nothing is kept in web storage.
import { expect, test, type Page } from "@playwright/test";
import { canvasReady, frame, mockCore, positionOf, small } from "./fixtures";

test.use({ viewport: { width: 1440, height: 900 } });

/** The modifier the screen reads for its shortcuts: Cmd where the page says it runs on a Mac, else Ctrl. */
const modOf = (page: Page) =>
  page.evaluate(() => (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "Meta" : "Control"));

const centreX = (box: { x: number; width: number } | null) => (box ? box.x + box.width / 2 : NaN);

test("opening a project from the switcher shows its files, Deliverables and team as frames", async ({ page }) => {
  const core = await mockCore(page, small(), { remembered: false });
  await page.goto("/");
  await expect(page.getByRole("banner", { name: "الشريط العلوي" }).getByRole("button", { name: "الشات العام" })).toBeVisible();

  await page.locator('[data-region="topbar"] [data-region-start]').click();
  await page.getByRole("button", { name: core.scene.project.name }).click();

  await canvasReady(page);
  for (const key of ["files:all", "file:spec", "team:core", "desk:pricing", "deliverable:takeoff", "deliverable:pricing", "deliverable:quotes", "deliverable:letter"] as const)
    await expect(frame(page, key)).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
  await expect(page.locator('[data-region="topbar"] [data-region-start]')).toContainText(core.scene.project.name);
  expect(core.unknown).toEqual([]);
});

test("the chrome mirrors in Arabic: the chat at the left, the zoom controls at the right", async ({ page }) => {
  await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  const canvas = centreX(await page.locator('[data-region="canvas"]').boundingBox());
  const chat = centreX(await page.locator('aside[data-region="chat"]').boundingBox());
  const zoom = centreX(await page.getByRole("toolbar", { name: "أدوات التكبير" }).boundingBox());
  const box = centreX(await page.locator("[data-command-box]").boundingBox());
  expect(chat).toBeLessThan(canvas);
  expect(zoom).toBeGreaterThan(canvas);
  expect(box).toBeGreaterThan(chat); // the command bar sits between the chat and the zoom controls
  expect(box).toBeLessThan(zoom);
  // the pane itself never flips: world coordinates are the same in both languages
  await expect(page.locator('section[aria-label="كانفاس المشروع"]')).toHaveAttribute("dir", "ltr");
});

test("in English the chrome is the other way round", async ({ page }) => {
  await mockCore(page, small(), { language: "en" });
  await page.goto("/");
  await canvasReady(page);
  const canvas = centreX(await page.locator('[data-region="canvas"]').boundingBox());
  expect(centreX(await page.locator('aside[data-region="chat"]').boundingBox())).toBeGreaterThan(canvas);
  expect(centreX(await page.getByRole("toolbar", { name: "Zoom controls" }).boundingBox())).toBeLessThan(canvas);
});

test("a dragged frame is saved to the core and is where it was after a reload", async ({ page }) => {
  const core = await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  const key = "deliverable:pricing";
  await expect(frame(page, key)).toBeVisible();
  const before = await positionOf(page, key);

  const strip = frame(page, key).locator("header h3");
  await strip.hover(); // also checks nothing covers the strip
  const box = (await strip.boundingBox())!;
  const saved = core.nextFrameSave((body) => body.frames.some((f) => f.key === key && f.x !== before.x));
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) await page.mouse.move(box.x + box.width / 2 + i * 24, box.y + box.height / 2 + i * 12);
  await page.mouse.up();
  const moved = (await saved).frames.find((f) => f.key === key)!;
  expect(moved.x).toBeGreaterThan(before.x);
  expect(moved.y).toBeGreaterThan(before.y);
  expect(await positionOf(page, key)).toEqual({ x: moved.x, y: moved.y });

  await page.reload();
  await canvasReady(page);
  expect(await positionOf(page, key)).toEqual({ x: moved.x, y: moved.y });
  expect(core.unknown).toEqual([]);
});

test("keyboard only: F6 to the canvas, Tab to a frame, Enter in, Esc out, / to the command bar, send with the selection", async ({ page }) => {
  const core = await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  const active = () => page.evaluate(() => document.activeElement?.closest("[data-region]")?.getAttribute("data-region") ?? null);

  await page.locator("body").focus();
  await page.keyboard.press("F6");
  expect(await active()).toBe("topbar");
  await page.keyboard.press("F6");
  expect(await active()).toBe("canvas");

  // Tab walks the frames (and the buttons on their strips) until a Deliverable frame has focus
  let key: string | undefined;
  for (let i = 0; i < 40 && !key; i++) {
    await page.keyboard.press("Tab");
    key = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return el?.matches('.react-flow__node[data-id^="deliverable:"]') ? el.dataset.id : undefined;
    });
  }
  expect(key).toBeDefined();

  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => !!document.activeElement?.closest("[data-frame-body]"))).toBe(true);
  await page.keyboard.press("Escape");
  expect(await page.evaluate(() => (document.activeElement as HTMLElement | null)?.dataset.id)).toBe(key);

  await page.keyboard.press("Slash");
  await expect(page.locator("[data-command-box]")).toBeFocused();
  await page.keyboard.type("راجع ده - عينة");
  await page.keyboard.press("Enter");
  await expect.poll(() => core.chats.length).toBe(1);
  expect(core.chats[0]!.selection).toEqual([expect.objectContaining({ kind: "deliverable", id: key!.slice("deliverable:".length) })]);
  await expect(page.locator('aside[data-region="chat"]')).toContainText("راجع ده - عينة");
});

test("F6 and Shift+F6 walk the four regions", async ({ page }) => {
  await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  const active = () => page.evaluate(() => document.activeElement?.closest("[data-region]")?.getAttribute("data-region") ?? null);
  await page.locator("body").focus();
  const forward: (string | null)[] = [];
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("F6");
    forward.push(await active());
  }
  expect(forward).toEqual(["topbar", "canvas", "chat", "command", "topbar"]);
  await page.keyboard.press("Shift+F6");
  expect(await active()).toBe("command");
});

test("Ctrl+K opens the palette by key code, with the Arabic layout too", async ({ page }) => {
  await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  const mod = await modOf(page);
  const palette = page.getByRole("dialog", { name: "بحث وأوامر" });

  await page.keyboard.press(`${mod}+KeyK`);
  await expect(palette).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(palette).toBeHidden();

  // the Arabic layout: the same key sends code KeyK with the key «ن»
  await page.evaluate((mod) => {
    const init = { code: "KeyK", key: "ن", bubbles: true, cancelable: true, ctrlKey: mod === "Control", metaKey: mod === "Meta" };
    document.body.dispatchEvent(new KeyboardEvent("keydown", init));
  }, mod);
  await expect(palette).toBeVisible();

  // the palette finds a frame by its title and focuses it
  await page.keyboard.type("مقارنة عروض");
  await expect(page.getByRole("option", { name: "مقارنة عروض الموردين - عينة" })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(palette).toBeHidden();
  await expect(frame(page, "deliverable:quotes")).toBeFocused();
});

test("a PDF frame brought into view shows its page image from the core", async ({ page }) => {
  await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  await page.keyboard.press(`${await modOf(page)}+KeyK`);
  await page.keyboard.type("المواصفات الفنية");
  await expect(page.getByRole("option", { name: "المواصفات الفنية - عينة.pdf" })).toBeVisible();
  await page.keyboard.press("Enter");
  const image = frame(page, "file:spec").getByRole("img", { name: /18/ });
  await expect(image).toBeVisible();
  await expect(image).toHaveJSProperty("naturalWidth", 2);
  expect(await image.getAttribute("src")).toMatch(/^blob:/);
});

test("a Deliverable that arrives on the live stream gets a frame, and no frame moves", async ({ page }) => {
  const core = await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
  const keys = ["files:all", "deliverable:pricing", "deliverable:letter", "team:core"] as const;
  const before = await Promise.all(keys.map((key) => positionOf(page, key)));
  const boq = { ...core.scene.deliverables[1]!, id: "boq2", title: "مقايسة معدلة - عينة", status: "draft" as const, code: null };
  core.emit([{ type: "deliverable", deliverable: boq }]);
  await expect(frame(page, "deliverable:boq2")).toHaveCount(1);
  await expect(page.locator(".react-flow__node")).toHaveCount(9);
  expect(await Promise.all(keys.map((key) => positionOf(page, key)))).toEqual(before);
});

test("Delete and Backspace never remove a frame", async ({ page }) => {
  await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  await frame(page, "deliverable:letter").locator("header h3").click();
  await page.keyboard.press("Delete");
  await page.keyboard.press("Backspace");
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
});

test("Arabic titles fit their name strips", async ({ page }) => {
  await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
  const overflowing = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".react-flow__node [data-frame] > header")].flatMap((strip) => {
      const title = strip.querySelector("h3")!;
      return title.scrollWidth > title.clientWidth || strip.scrollWidth > strip.clientWidth ? [title.textContent] : [];
    }),
  );
  expect(overflowing).toEqual([]);
});

test("nothing is kept in web storage beyond the language and the project id", async ({ page }) => {
  const core = await mockCore(page, small());
  await page.goto("/");
  await canvasReady(page);
  // move a frame, pan, zoom, fold a frame, send a message: everything goes to the core
  const strip = frame(page, "deliverable:quotes").locator("header h3");
  await strip.hover();
  const box = (await strip.boundingBox())!;
  await page.mouse.down();
  await page.mouse.move(box.x + 80, box.y + 60, { steps: 6 });
  await page.mouse.up();
  await frame(page, "deliverable:quotes").getByRole("button", { name: "اطوي الإطار" }).click();
  await page.mouse.move(700, 450);
  await page.mouse.wheel(0, 300);
  await page.getByRole("button", { name: "كبّر" }).click();
  await page.locator("[data-command-box]").fill("اكتب خطاب العطاء - عينة");
  await page.keyboard.press("Enter");
  await expect.poll(() => core.chats.length).toBe(1);
  await expect.poll(() => core.viewSaves.length, { timeout: 5000 }).toBeGreaterThan(0);
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pagehide")));

  const stored = await page.evaluate(async () => ({
    local: Object.keys(localStorage).sort(),
    session: Object.keys(sessionStorage),
    databases: "databases" in indexedDB ? (await indexedDB.databases()).map((d) => d.name) : [],
  }));
  expect(stored).toEqual({ local: ["qsone.language", "qsone.project"], session: [], databases: [] });
});
