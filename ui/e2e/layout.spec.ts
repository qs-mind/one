// The workspace's layout, measured in a real browser: the open document at the inline start (right in Arabic) and
// the chat beside it at the end, never under it; the sheet 8 px under the top bar and 8 px above the window's foot;
// one message box at the chat's foot; the placeholder whole at every width, the project's name and (from 1000 px)
// the document's title never cut, the status folding into More before anything clips, nothing in the top bar run
// over another and «الأرقام عينة» said whole even with a long project name; More status shown at 1280 px; a document picked from the switcher shown in place, kept in the project
// (a reload opens it) and left with Back; below 1000 px the chat a panel over the document; below 640 px the
// document the window's width.
import { expect, test, type Locator } from "@playwright/test";
import { count, texts } from "../src/i18n";
import { documentRegion, mockCore, openDocument, shownWhole, small, switcher, workspaceReady } from "./fixtures";

type Box = { x: number; y: number; width: number; height: number };
const box = async (l: Locator) => (await l.boundingBox())!;
const overlaps = (a: Box, b: Box) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

/** Whether the element's text is all shown: nothing hidden past its edges. */
const whole = (l: Locator) => l.evaluate((el) => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1);

for (const language of ["ar", "en"] as const) {
  test(`the document at the inline start, the chat beside it and never over it, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockCore(page, small(), { language });
    await page.goto("/");
    await workspaceReady(page, page.getByRole("grid"));
    const sheet = await box(page.locator("[data-document-sheet]"));
    const chat = await box(page.locator('aside[data-region="chat"]'));
    const bar = await box(page.locator('[data-region="topbar"]'));
    expect(overlaps(sheet, chat)).toBe(false);
    if (language === "ar") expect(sheet.x).toBeGreaterThan(chat.x);
    else expect(sheet.x).toBeLessThan(chat.x);
    // dense: 8 px under the top bar and above the window's foot, 12 px from the window's side
    expect(Math.abs(sheet.y - (bar.y + bar.height) - 8)).toBeLessThanOrEqual(1);
    expect(Math.abs(900 - (sheet.y + sheet.height) - 8)).toBeLessThanOrEqual(1);
    const side = language === "ar" ? 1440 - (sheet.x + sheet.width) : sheet.x;
    expect(Math.abs(side - 12)).toBeLessThanOrEqual(1);
    // the document's title is in the top bar, after the project's name; its state beside it
    await expect(switcher(page)).toContainText("تسعير المقايسة - عينة");
    await expect(page.locator('[data-region="topbar"]')).toContainText(texts.sampleNumbers[language]);
  });

  test(`one message box, at the open chat's foot, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockCore(page, small(), { language });
    await page.goto("/");
    await workspaceReady(page);
    const chat = page.locator('aside[data-region="chat"]');
    await expect(page.locator("[data-command-box]")).toHaveCount(1);
    await expect(chat.locator("[data-command-box]")).toBeVisible();
    const input = await box(chat.locator("[data-command-box]"));
    const panel = await box(chat);
    expect(panel.y + panel.height - (input.y + input.height)).toBeLessThan(40);
  });

  for (const width of [1024, 1280, 1440]) {
    test(`the placeholder, the top bar and the document's title are whole at ${width} px, ${language}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const scene = small();
      scene.project.name = language === "ar" ? "برج إداري بالعاصمة الإدارية الجديدة - عينة" : "Administrative tower, New Capital (sample)";
      await mockCore(page, scene, { language });
      await page.goto("/");
      await workspaceReady(page);
      // the box shows its whole placeholder
      const input = page.locator("[data-command-box]");
      expect(await whole(input)).toBe(true);
      const mirror = await box(page.locator("[data-command-mirror]"));
      const shown = await box(input);
      expect(Math.abs(mirror.height - shown.height)).toBeLessThan(2);
      // the project's name and the document's title are never cut
      expect(await whole(page.locator('[data-region="topbar"] [data-region-start] span[dir="auto"]'))).toBe(true);
      expect(await whole(switcher(page))).toBe(true);
      // nothing in the top bar spills past its edges, and the status shows whole or folds into More status
      const bar = await box(page.locator('[data-region="topbar"]'));
      for (const item of await page.locator('[data-region="topbar"] button:visible').all()) {
        const b = await box(item);
        expect(b.x).toBeGreaterThanOrEqual(bar.x - 1);
        expect(b.x + b.width).toBeLessThanOrEqual(bar.x + bar.width + 1);
      }
      for (const item of await page.locator('[data-status]:not([aria-hidden="true"])').all()) {
        const strip = await box(item.locator(".."));
        const b = await box(item);
        expect(b.x).toBeGreaterThanOrEqual(strip.x - 1);
        expect(b.x + b.width).toBeLessThanOrEqual(strip.x + strip.width + 1);
      }
      // at 1280 px the long name leaves the status no room: what folds is under More status, and that is seen whole
      if (width === 1280) {
        const more = page.locator('[data-region="topbar"] [data-status="more"]');
        await expect(more).toBeVisible();
        expect(await shownWhole(more), "More status is seen whole").toBe(true);
      }
    });
  }

  test(`at 1440 px the top bar shows two status items, the submission and the items left, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockCore(page, small(), { language });
    await page.goto("/");
    await workspaceReady(page);
    const shown = page.locator('[data-region="topbar"] [data-status]:not([data-status="more"]):not([aria-hidden="true"])');
    await expect(shown).toHaveCount(2);
    await expect(shown.nth(0)).toHaveAttribute("data-status", "submission");
    await expect(shown.nth(1)).toHaveAttribute("data-status", "left");
    await expect(shown.nth(1)).toHaveText(count("itemsLeft", 240, {}, language));
    for (const item of await shown.all()) expect(await shownWhole(item)).toBe(true);
  });

  const names = {
    short: { ar: "مبنى إداري - عينة", en: "Office building (sample)" },
    long: { ar: "برج إداري بالعاصمة الإدارية الجديدة - عينة", en: "Administrative tower, New Capital (sample)" },
  };
  for (const width of [640, 1000])
    for (const name of ["short", "long"] as const)
    test(`at ${width} px with a ${name} project name nothing in the top bar runs over another, and «الأرقام عينة» is whole, ${language}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      const scene = small();
      // the name and the waiting words take the bar's room: the state, then the title (to a few words), then the name give
      scene.project.name = names[name][language];
      scene.status = { ...scene.status, waiting: 1 };
      await mockCore(page, scene, { language });
      await page.goto("/");
      await workspaceReady(page);
      const bar = page.locator('[data-region="topbar"]');
      // the bar's own items, side by side: the project, the document's title, what waits, search, the chat, More
      const label = bar.locator("[data-sample-label]");
      const items = [page.locator('[data-region="topbar"] [data-region-start]'), switcher(page), label, ...(await bar.locator("button:visible").all())];
      const boxes = [];
      for (const item of items) boxes.push(await box(item));
      for (const [i, a] of boxes.entries())
        for (const b of boxes.slice(i + 1)) {
          const apart = a.x + a.width <= b.x + 1 || b.x + b.width <= a.x + 1;
          const inside = (a.x >= b.x - 1 && a.x + a.width <= b.x + b.width + 1) || (b.x >= a.x - 1 && b.x + b.width <= a.x + a.width + 1);
          expect(apart || inside, "two items of the top bar run over each other").toBe(true);
        }
      if (width >= 1000) await expect(bar).toContainText(count("decisionsWaiting", 1, {}, language));
      await expect(label).toContainText(texts.sampleNumbers[language]);
      expect(await shownWhole(label), "«الأرقام عينة» is seen whole").toBe(true);
      // the title keeps a few words: its button never shrinks to the ▾ alone
      expect((await box(switcher(page))).width, "the title keeps a few words").toBeGreaterThanOrEqual(80);
    });

  test(`a document picked from the switcher shows in place, is kept, and Back returns, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const core = await mockCore(page, small(), { language });
    await page.goto("/");
    await workspaceReady(page, page.getByRole("grid"));
    const saved = core.nextWorkspaceSave((w) => w.open === "deliverable:letter");
    await openDocument(page, /خطاب العطاء - مسودة عينة/);
    await expect(documentRegion(page)).toHaveAttribute("aria-label", "خطاب العطاء - مسودة عينة");
    await expect(documentRegion(page).getByText("الأسعار سارية لمدة ٣٠ يوماً - نص عينة")).toBeVisible();
    await expect(page.getByRole("menu")).toHaveCount(0);
    expect((await saved).open).toBe("deliverable:letter");

    // the project keeps it: a reload opens on the letter
    await page.reload();
    await workspaceReady(page);
    await expect(documentRegion(page)).toHaveAttribute("aria-label", "خطاب العطاء - مسودة عينة");

    // Back, by the arrow that points back in the page's direction, from the BOQ to the letter
    await openDocument(page, /تسعير المقايسة - عينة/);
    await expect(page.getByRole("grid")).toBeVisible();
    await page.locator("body").click({ position: { x: 4, y: 890 } }); // focus out of the menu, not in a field
    await page.keyboard.press(language === "ar" ? "Alt+ArrowRight" : "Alt+ArrowLeft");
    await expect(documentRegion(page)).toHaveAttribute("aria-label", "خطاب العطاء - مسودة عينة");
  });

  test(`a five-column table card shows every column whole in the chat, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const scene = small();
    await mockCore(page, scene, { language });
    await page.route(`**/api/chat/${scene.project.id}/messages`, (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ messages: priceProposal() }) }),
    );
    await page.goto("/");
    await workspaceReady(page);
    const chat = await box(page.locator('aside[data-region="chat"]'));
    const card = page.locator('[data-card="c1"]');
    await expect(card).toBeVisible();
    const b = await box(card);
    expect(b.x).toBeGreaterThanOrEqual(chat.x);
    expect(b.x + b.width).toBeLessThanOrEqual(chat.x + chat.width);
    // at the chat's width every column shows whole inside the card: the rows stack, nothing scrolls or is cut
    expect(await card.locator("[data-rows-scroll]").evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    for (const cell of await card.locator("td[dir=auto]").all()) {
      const c = await box(cell);
      expect(c.x).toBeGreaterThanOrEqual(b.x);
      expect(c.x + c.width).toBeLessThanOrEqual(b.x + b.width);
      expect(await cell.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    }
  });

  test(`the first project's backup ask keeps its words one block in the chat, its buttons under them, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const scene = small();
    scene.others = []; // the project about to be made is the only one, and no backup folder is picked: ONE asks once
    await mockCore(page, scene, { language });
    await page.route("**/api/backup", (route) => route.fulfill({ json: { folder: null } }));
    await page.route("**/api/projects", (route) =>
      route.request().method() === "POST" ? route.fulfill({ json: scene.project }) : route.fallback(),
    );
    await page.goto("/");
    await workspaceReady(page);
    await page.locator('[data-region="topbar"] [data-region-start]').click();
    await page.getByRole("button", { name: texts.newProject[language] }).click();
    await page.getByLabel(texts.projectName[language]).fill(scene.project.name);
    await page.getByLabel(texts.projectName[language]).press("Enter");
    const ask = page.getByRole("region", { name: texts.backupTitle[language] });
    await expect(ask).toContainText(texts.backupAskFolder[language]);
    const chat = await box(page.locator('aside[data-region="chat"]'));
    expect(chat.width, "a chat about 320 px wide").toBeLessThanOrEqual(340);
    const words = await box(ask.locator("p").first());
    expect(words.width, "never a word a line").toBeGreaterThan(200);
    for (const name of [texts.backupPickFolder[language], texts.backupLater[language]]) {
      const button = await box(ask.getByRole("button", { name, exact: true }));
      expect(button.y, `${name} wraps under the words`).toBeGreaterThanOrEqual(words.y + words.height - 1);
    }
  });

  test(`below 1000 px the chat is a panel over the document, from the top bar, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 800 });
    await mockCore(page, small(), { language });
    await page.goto("/");
    await workspaceReady(page);
    await expect(page.locator('aside[data-region="chat"]')).toHaveCount(0);
    const sheet = await box(page.locator("[data-document-sheet]"));
    expect(sheet.width).toBeGreaterThan(900 - 2 * 12 - 2); // the document has the width
    const button = page.locator("[data-chat-button]");
    await button.click();
    const chat = page.locator('aside[data-region="chat"]');
    await expect(chat).toBeVisible();
    const panel = await box(chat);
    expect(overlaps(panel, sheet)).toBe(true); // over the document, at the inline end
    if (language === "ar") expect(panel.x).toBeLessThan(sheet.x + sheet.width / 2);
    else expect(panel.x + panel.width).toBeGreaterThan(sheet.x + sheet.width / 2);
    await page.keyboard.press("Escape");
    await expect(chat).toHaveCount(0);
    await expect(button).toBeFocused();
  });

  test(`below 640 px the document takes the window's width, ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 800 });
    await mockCore(page, small(), { language });
    await page.goto("/");
    await workspaceReady(page, page.getByRole("grid"));
    const sheet = await box(page.locator("[data-document-sheet]"));
    expect(sheet.x).toBeLessThanOrEqual(1);
    expect(sheet.width).toBeGreaterThanOrEqual(598);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); // no page scroll sideways
  });
}

/** The chat as prices_propose leaves it: one table card waiting, five columns (sample data). */
function priceProposal() {
  const rows = [
    { description: "بالمتر المكعب خرسانة مسلحة للأعمدة والكمرات طبقاً للمواصفات - عينة", unit: "م3", rate: "4150.00", currency: "EGP", vat: "14%" },
    { description: "بالطن حديد تسليح عالي المقاومة - عينة", unit: "طن", rate: "38500.00", currency: "EGP", vat: "14%" },
    { description: "بالمتر المربع بلاط بورسلين 60×60 - عينة", unit: "م2", rate: "620.00", currency: "EGP", vat: "14%" },
  ];
  return [
    { id: "u1", role: "user", parts: [{ type: "text", text: "سعّر بنود الخرسانة والحديد - عينة" }] },
    {
      id: "a1",
      role: "assistant",
      parts: [
        {
          type: "data-card",
          id: "c1",
          data: {
            kind: "rows",
            title: { en: "Keep these prices?", ar: "احفظ الأسعار دي؟" },
            detail: { en: "Tick the rows to keep (sample data).", ar: "علّم على الصفوف اللي تتحفظ - عينة." },
            options: ["keep", "no"],
            status: "pending",
            payload: {
              columns: [
                { key: "description", label: { en: "Item", ar: "البند" } },
                { key: "unit", label: { en: "Unit", ar: "الوحدة" } },
                { key: "rate", label: { en: "Rate", ar: "السعر" } },
                { key: "currency", label: { en: "Currency", ar: "العملة" } },
                { key: "vat", label: { en: "VAT", ar: "الضريبة" } },
              ],
              rows,
              tick: true,
            },
          },
        },
      ],
    },
  ];
}
