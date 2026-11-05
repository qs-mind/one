// Calm motion on the real app and core, with the bench's fake AI (docs/specs/2026-11-05-motion-design.md, motions 1, 2
// and 6): a scroll area fades only at an edge with more beyond it; the sheet's total rolls to the core's new value
// when an accepted edit changes it; AI settings ease to a new height as a refused cap's line comes and goes; the
// first-launch bar stays on screen with a two-line failure, also 380 px wide and at 200% zoom.
// Screenshots (1440×900): test-results/bench/shots, and as mo-B-NN-<state>-<ar|en>.png in $QSONE_MOTION_SHOTS when it
// is set, with the roll and the height on video there as mo-roll-<ar|en>.webm and mo-height-<ar|en>.webm.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import type { Browser, Locator, Page } from "@playwright/test";
import { texts } from "../src/i18n";
import { formatDecimal } from "../src/viewers/sheet/format";
import { expect, test, Walk } from "./bench";

const benchPort = Number(process.env.QSONE_BENCH_PORT || 1442);
const settingsFile = path.join(tmpdir(), benchPort === 1442 ? "qs-mind-one-bench" : `qs-mind-one-bench-${benchPort}`, "data", "settings.json");
const shotsDir = path.join("test-results", "bench", "shots");
const videoDir = path.join("test-results", "bench", "video");
const extra = process.env.QSONE_MOTION_SHOTS;
const VIEW = { width: 1440, height: 900 };

// A sample key, not a real one: the bench refuses any key without "-bench-ok-" in it.
const REFUSED = "sk-ant-sample-not-a-real-key-refused-00000000000000";

type Lang = "ar" | "en";
const ORDER = [
  "fade-none",
  "fade-bottom",
  "fade-both",
  "fade-top",
  "height-before",
  "height-after",
  "total-before",
  "total-rolling",
  "total-after",
  "bar-failed",
  "bar-failed-380",
  "bar-failed-zoom200",
];
const say = (lang: Lang, key: keyof typeof texts) => texts[key][lang];

async function shot(page: Page, state: string, lang: Lang, settle = 450) {
  if (settle) await page.waitForTimeout(settle); // a fade or a line has settled
  const name = `mo-B-${String(ORDER.indexOf(state) + 1).padStart(2, "0")}-${state}-${lang}.png`;
  mkdirSync(shotsDir, { recursive: true });
  const file = path.join(shotsDir, name);
  await page.screenshot({ path: file });
  if (extra) {
    mkdirSync(extra, { recursive: true });
    copyFileSync(file, path.join(extra, name));
  }
}

/** A page of its own, on video, in `lang`, with `project` open. */
async function recorded(browser: Browser, lang: Lang, project?: string) {
  const context = await browser.newContext({ viewport: VIEW, recordVideo: { dir: videoDir, size: VIEW } });
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await context.addInitScript(
    ([language, id]) => {
      localStorage.setItem("qsone.language", language!);
      if (id) localStorage.setItem("qsone.project", id);
    },
    [lang, project ?? ""],
  );
  return { context, page: await context.newPage() };
}

async function keepVideo(page: Page, name: string) {
  await page.context().close();
  const file = path.join(videoDir, name);
  await page.video()!.saveAs(file);
  if (extra) copyFileSync(file, path.join(extra, name));
}

/** Pastes `text` into the focused field, as the engineer does: through the clipboard. */
async function paste(page: Page, text: string) {
  await page.evaluate((value) => navigator.clipboard.writeText(value), text);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("ControlOrMeta+v");
}

const edges = (area: Locator) =>
  area.evaluate((el) => ({
    top: el.hasAttribute("data-more-top"),
    bottom: el.hasAttribute("data-more-bottom"),
    mask: getComputedStyle(el).maskImage || getComputedStyle(el).getPropertyValue("-webkit-mask-image"),
  }));

async function inView(page: Page, button: Locator, why: string) {
  const box = await button.boundingBox();
  const { width, height } = page.viewportSize()!;
  expect(box, why).not.toBeNull();
  expect(box!.x >= 0 && box!.y >= 0 && box!.x + box!.width <= width && box!.y + box!.height <= height, `${why}: ${JSON.stringify(box)} in ${width}×${height}`).toBe(true);
}

/** An expected refusal is not a problem of the walk: neither its HTTP status nor the browser's console line for it. */
function expected(walk: Walk, status: number, request: string) {
  for (const line of [`HTTP ${status} ${request}`, `status of ${status} `]) {
    const at = walk.problems.findIndex((problem) => problem.includes(line));
    if (at >= 0) walk.problems.splice(at, 1);
  }
}

async function openAiSettings(page: Page, lang: Lang) {
  await page.locator('[data-region="topbar"]').getByRole("button", { name: say(lang, "more"), exact: true }).click();
  await page.getByRole("button", { name: say(lang, "ai"), exact: true }).click();
  const heading = page.getByRole("heading", { name: say(lang, "aiTitle") }).first();
  await expect(heading).toBeVisible();
  return page.locator(".scroll-fade").filter({ has: heading }).first();
}

test.use({ actionTimeout: 20_000 }); // a missing button fails at once, not at the walk's end

for (const lang of ["ar", "en"] as const) {
  test(`scroll edges, a rolling total, heights that ease and the first-launch bar (${lang})`, async ({ walk, page, browser }) => {
    test.setTimeout(360_000);
    await walk.start(lang);

    // 1. Scroll edges --------------------------------------------------------------------------------------------
    // the palette's list, when what it lists fits: no fade
    await page.keyboard.press("Control+k");
    await page.keyboard.type(lang === "ar" ? "مشروع" : "project");
    const list = page.locator("[cmdk-list]");
    await expect(list.getByRole("option").first()).toBeVisible(); // a short list, not "Nothing found"
    await expect.poll(() => edges(list)).toMatchObject({ top: false, bottom: false, mask: "none" });
    await shot(page, "fade-none", lang);
    await page.keyboard.press("Escape");

    // AI settings, longer than the window: the bottom fades at the top, both in the middle, the top at the end
    const panel = await openAiSettings(page, lang);
    await expect.poll(() => panel.evaluate((el) => el.scrollHeight > el.clientHeight + 100), "AI settings scroll in the panel").toBe(true);
    await expect.poll(() => edges(panel)).toMatchObject({ top: false, bottom: true });
    expect((await edges(panel)).mask).toContain("linear-gradient");
    await shot(page, "fade-bottom", lang);
    await panel.evaluate((el) => el.scrollTo({ top: (el.scrollHeight - el.clientHeight) / 2 }));
    await expect.poll(() => edges(panel)).toMatchObject({ top: true, bottom: true });
    await shot(page, "fade-both", lang);
    await panel.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
    await expect.poll(() => edges(panel)).toMatchObject({ top: true, bottom: false });
    await shot(page, "fade-top", lang);
    await page.keyboard.press("Escape");

    // 2. AI settings ease to their new height when a line comes and goes (a refused cap), on video ----------------
    {
      const { page: own } = await recorded(browser, lang);
      await own.goto("/");
      await own.waitForTimeout(800);
      const area = await openAiSettings(own, lang);
      const section = area.locator("section").filter({ has: own.getByRole("heading", { name: say(lang, "aiTitle") }) });
      const day = section.getByLabel(say(lang, "capDay"));
      await expect(day).not.toHaveValue("");
      const was = await day.inputValue();
      await day.scrollIntoViewIfNeeded();
      await area.evaluate((el) => el.scrollBy({ top: 160 })); // the line's place in view too
      // each height the section eases between, as it asks the browser to animate it
      await section.evaluate((el) => {
        const box = el.firstElementChild as HTMLElement & { eased?: Keyframe[][] };
        const animate = box.animate.bind(box);
        box.eased = [];
        box.animate = (keyframes, options) => (box.eased!.push(keyframes as Keyframe[]), animate(keyframes, options));
      });
      const eased = async () =>
        (await section.evaluate((el) => (el.firstElementChild as HTMLElement & { eased: Keyframe[][] }).eased)).map(([a, b]) => [
          parseFloat(String(a!.height)),
          parseFloat(String(b!.height)),
        ]);
      await own.mouse.move(0, 0);
      await shot(own, "height-before", lang);
      await day.fill("16,5");
      await day.press("Tab"); // leaving the field saves what it holds: the core refuses it
      const form = day.locator("xpath=ancestor::form");
      await expect(form.getByRole("alert")).toBeVisible();
      await expect.poll(async () => (await eased()).some(([a, b]) => b! > a!), "the section eases to a taller box").toBe(true);
      await own.mouse.move(0, 0);
      await shot(own, "height-after", lang, 600);
      await day.fill(was); // as the bench had it
      await day.press("Tab");
      await expect(form.getByRole("alert")).toHaveCount(0);
      await expect.poll(async () => (await eased()).some(([a, b]) => b! < a!), "and back to a shorter one").toBe(true);
      await own.waitForTimeout(800);
      await keepVideo(own, `mo-height-${lang}.webm`);
    }

    // 3. The total rolls when an accepted edit changes it, on video ------------------------------------------------
    await walk.createProject(lang === "ar" ? "مشروع عينة للحركة - منصة الاختبار" : "Sample motion - test bench");
    await walk.addFiles();
    await walk.brief(lang === "ar" ? "bench:deliverable جهّز جدول الكميات المسعّر وخطاب العطاء" : "bench:deliverable Make the priced BOQ and the cover letter");
    {
      // one project is open at a time: this page leaves it for the General chat, so the recorded page can open it
      const projectName = lang === "ar" ? "مشروع عينة للحركة - منصة الاختبار" : "Sample motion - test bench";
      await page.locator('[data-region="topbar"]').getByRole("button", { name: projectName }).click();
      await page.getByRole("button", { name: say(lang, "generalChat"), exact: true }).click();
      await expect(page.locator('[data-region="topbar"]').getByRole("button", { name: walk.w.general })).toBeVisible();
      const { page: own } = await recorded(browser, lang, walk.projectId);
      await own.goto("/");
      await expect(own.locator('[data-region="topbar"]').getByRole("button", { name: projectName })).toBeVisible();
      // a reopened project's chat shows no cards: the BOQ opens from the Project Index
      await own.locator('[data-region="topbar"]').getByRole("button", { name: say(lang, "deliverablesButton") }).click();
      const index = own.locator('section[aria-labelledby="project-index"]');
      await index.getByRole("button", { name: lang === "ar" ? /جدول كميات/ : /BOQ/ }).first().click();
      await index.getByRole("button", { name: say(lang, "close"), exact: true }).click(); // it opened full screen
      await own.waitForTimeout(1200);
      const listed = (await (await own.request.get(`/api/projects/${walk.projectId}/deliverables`)).json()) as {
        deliverables: { id: string; kind: string }[];
      };
      const deliverableId = listed.deliverables.find((d) => d.kind === "sheet")!.id;
      const grid = own.getByRole("grid").last();
      const total = grid.locator("button.font-bold").last();
      await expect(total).toBeAttached();
      await total.scrollIntoViewIfNeeded(); // the total's column is the last: in view, with the rate's beside it
      const was = (await total.textContent())!.trim();
      await shot(own, "total-before", lang);

      // a rate: the column whose header says so, in the first row that has a number there
      const rateLabel = lang === "ar" ? /الفئة|السعر/ : /Rate/;
      const header = grid.getByRole("columnheader", { name: rateLabel }).first();
      const column = await header.getAttribute("aria-colindex");
      const cell = grid.locator(`[role="gridcell"][aria-colindex="${column}"]`).filter({ hasText: /\d/ }).first();
      await cell.dblclick();
      const editor = grid.getByRole("textbox"); // the cell's text is in the editor now, so the cell's filter no longer holds
      const old = await editor.inputValue();
      await editor.fill(String(Math.round(Number(old) * 1.5)));
      await editor.press("Enter");
      const accept = grid.getByRole("button", { name: say(lang, "sheetAccept") }).first();
      await expect(accept).toBeVisible();
      await own.waitForTimeout(600);
      await accept.click();
      await expect(grid.locator("[data-roll]").first(), "the total rolls").toBeAttached();
      await shot(own, "total-rolling", lang, 150);
      await expect(grid.locator("[data-roll]")).toHaveCount(0);
      const view = (await (await own.request.get(`/api/projects/${walk.projectId}/deliverables/${deliverableId}`)).json()) as {
        total: { value: string; currency?: string | null };
      };
      const now = formatDecimal(view.total.value, view.total.currency ? 2 : undefined);
      expect(now, "an accepted edit changed the core's total").not.toBe(was);
      await expect(total, "the total ends on the core's new value").toHaveText(now);
      await shot(own, "total-after", lang);
      await own.waitForTimeout(400);
      await keepVideo(own, `mo-roll-${lang}.webm`);
    }

    // 4. The first-launch bar: a two-line failure in Connect AI never moves Next or pushes it out of sight ---------
    const saved = JSON.parse(readFileSync(settingsFile, "utf8")) as Record<string, unknown>;
    delete saved.ai_consent;
    writeFileSync(settingsFile, JSON.stringify(saved));
    await page.reload();
    await page.locator('[data-region="chat"]').getByRole("button", { name: say(lang, "connectAi"), exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: say(lang, "consentAgree"), exact: true }).click();
    await dialog.getByRole("button", { name: new RegExp(`^${say(lang, "aiLinkApiKey")}`) }).click();
    const next = dialog.getByRole("button", { name: say(lang, "setupNext"), exact: true });
    const skip = dialog.getByRole("button", { name: say(lang, "setupSkip"), exact: true });
    const before = await next.boundingBox();
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await dialog.getByLabel(say(lang, "aiKeyLabel")).click();
    await paste(page, REFUSED);
    await expect(dialog.getByRole("alert")).toBeVisible();
    expected(walk, 409, "POST /api/settings/ai/check");
    await page.mouse.move(0, 0);
    await shot(page, "bar-failed", lang);
    expect(await next.boundingBox(), "the failure never moves Next").toEqual(before);
    await inView(page, next, "Next with the failure, 1440×900");
    for (const [width, height, state] of [[380, 900, "bar-failed-380"], [720, 450, "bar-failed-zoom200"]] as const) {
      await page.setViewportSize({ width, height });
      await dialog.getByRole("alert").scrollIntoViewIfNeeded(); // the failure and the bar in one view
      await shot(page, state, lang);
      await inView(page, next, `Next, ${state}`);
      await inView(page, skip, `Skip, ${state}`);
    }
    await page.setViewportSize(VIEW);
    await skip.click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
}
