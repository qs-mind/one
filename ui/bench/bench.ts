// Helpers for the bench walks: the real app with the fake AI of core/tests/bench (see playwright.bench.config.ts).
// A walk records every console error, page error and failed /api request, and fails with them at the end; problems
// found on the way (a card that only shows after a reload, a frame that does not come) are soft failures with a
// screenshot, so one run lists them all.
import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test as base, type Locator, type Page, type TestInfo } from "@playwright/test";

export const samplesDir = path.join(tmpdir(), "qs-mind-one-bench", "samples");
const shotsDir = path.join("test-results", "bench", "shots");
const MARK = /bench reply|رد تجريبي/;

type Lang = "ar" | "en";
const words = {
  ar: {
    general: "الشات العام",
    projectName: "اسم المشروع",
    create: "إنشاء",
    records: "سجلات المشروع",
    message: "رسالة إلى كبير مهندسي الكميات",
    send: "إرسال",
    stop: "إيقاف",
    keepTicked: "احفظ الصفوف المعلّمة",
    yes: "أيوه",
    open: "افتح",
    zoomOut: "صغّر",
    done: /ردّك:|مبقاش له لازمة/,
  },
  en: {
    general: "General chat",
    projectName: "Project name",
    create: "Create",
    records: "Project Records",
    message: "Message to the Lead QS",
    send: "Send",
    stop: "Stop",
    keepTicked: "Keep the ticked rows",
    yes: "Yes",
    open: "Open",
    zoomOut: "Zoom out",
    done: /Your answer:|No longer needed\./,
  },
} as const;

export class Walk {
  readonly problems: string[] = [];
  lang: Lang = "ar";
  projectId?: string;
  private n = 0;

  constructor(
    readonly page: Page,
    private readonly info: TestInfo,
  ) {
    page.on("console", (m) => {
      if (m.type() === "error") this.problems.push(`console error: ${m.text().slice(0, 500)} (at ${page.url()})`);
    });
    page.on("pageerror", (e) => this.problems.push(`page error: ${e.message.slice(0, 500)}`));
    page.on("response", (r) => {
      if (r.url().includes("/api/") && r.status() >= 400)
        this.problems.push(`HTTP ${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`);
    });
    page.on("requestfailed", (r) => {
      const why = r.failure()?.errorText ?? "";
      // a stream the page itself closes (leaving a project, a reload) is aborted, not failed
      if (r.url().includes("/api/") && !why.includes("ERR_ABORTED"))
        this.problems.push(`request failed: ${r.method()} ${new URL(r.url()).pathname}: ${why}`);
    });
  }

  get w() {
    return words[this.lang];
  }

  get chat(): Locator {
    return this.page.locator('[data-region="chat"]');
  }

  /** A full-page screenshot in test-results/bench/shots, copied to $QSONE_BENCH_SHOTS when it is set. */
  async shot(name: string) {
    this.n += 1;
    const slug = this.info.title.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
    const file = path.join(shotsDir, `${slug}-${String(this.n).padStart(2, "0")}-${name}.png`);
    mkdirSync(shotsDir, { recursive: true });
    await this.page.screenshot({ path: file, fullPage: true });
    const extra = process.env.QSONE_BENCH_SHOTS;
    if (extra) {
      mkdirSync(extra, { recursive: true });
      const next = readdirSync(extra).filter((f) => f.endsWith(".png")).length + 1;
      copyFileSync(file, path.join(extra, `${String(next).padStart(2, "0")}-${slug}-${name}.png`));
    }
    return file;
  }

  /** A soft failure with its screenshot: the walk goes on. */
  async problem(what: string, name: string) {
    const file = await this.shot(name);
    this.problems.push(`${what} (screenshot ${file})`);
  }

  async start(lang: Lang = "ar") {
    await this.page.goto("/");
    await expect(this.page.getByRole("textbox", { name: words.ar.message }).or(this.page.getByRole("textbox", { name: words.en.message }))).toBeVisible();
    if (lang === "en") await this.page.getByRole("button", { name: "English", exact: true }).click();
    this.lang = lang;
    await expect(this.page.getByRole("textbox", { name: this.w.message })).toBeVisible();
  }

  async createProject(name: string) {
    const top = this.page.locator('[data-region="topbar"]');
    await top.getByRole("button", { name: this.w.general }).click();
    await this.page.getByLabel(this.w.projectName).fill(name);
    await this.page.getByRole("button", { name: this.w.create, exact: true }).click();
    await expect(top.getByRole("button", { name })).toBeVisible();
    await expect(this.page.locator('[data-region="canvas"]')).toBeVisible();
    const list = (await (await this.page.request.get("/api/projects")).json()) as { projects: { id: string; name: string }[] };
    this.projectId = list.projects.find((p) => p.name === name)?.id;
    expect(this.projectId, "the new project is listed").toBeTruthy();
  }

  /** The sample files, through Project Records' Add files, as the engineer adds them. */
  async addFiles() {
    const names = readdirSync(samplesDir);
    await this.page.getByRole("button", { name: this.w.records, exact: true }).click();
    await this.page.locator('input[type="file"]').setInputFiles(names.map((f) => path.join(samplesDir, f)));
    for (const name of names) await expect(this.page.getByText(name.replace(/\.[^.]+$/, "").slice(0, 12)).first()).toBeVisible();
    await this.page.waitForTimeout(1500); // the canvas has had time to hear of them
    const files = this.page.locator('[data-frame="files:all"]');
    for (const name of names) {
      if (!(await files.getByText(name.slice(0, 12)).count()))
        await this.problem(`files added in Project Records are not on the canvas's Project files frame without a reload: ${name}`, "files-frame-not-live");
    }
    await this.page.getByRole("button", { name: this.lang === "ar" ? "إغلاق" : "Close", exact: true }).click();
  }

  private async waiting(): Promise<number> {
    if (!this.projectId) return 0;
    const r = await this.page.request.get(`/api/projects/${this.projectId}/status`);
    return r.ok() ? (((await r.json()) as { waiting?: number }).waiting ?? 0) : 0;
  }

  private pendingCard(): Locator {
    return this.chat.locator("section.border-copper").filter({ has: this.page.locator("button") }).filter({ hasNotText: this.w.done });
  }

  private stopButton(): Locator {
    return this.page.locator('[data-region="command"]').getByRole("button", { name: this.w.stop, exact: true });
  }

  /** Sends a Brief and answers every card as it comes, until the Brief ends. Returns the kinds answered. */
  async brief(text: string, { timeout = 180_000 } = {}): Promise<string[]> {
    const marks = await this.chat.getByText(MARK).count();
    await this.page.getByRole("textbox", { name: this.w.message }).fill(text);
    await this.page.getByRole("button", { name: this.w.send, exact: true }).click();
    await expect(this.chat.getByText(text.slice(0, 20)).first()).toBeVisible();
    await this.shot("brief-sent");
    const answered: string[] = [];
    const end = Date.now() + timeout;
    let unseenSince: number | undefined;
    while (Date.now() < end) {
      const card = this.pendingCard().first();
      if (await card.isVisible()) {
        unseenSince = undefined;
        answered.push(await this.answer(card));
        continue;
      }
      const waiting = await this.waiting();
      if (waiting > 0) {
        unseenSince ??= Date.now();
        if (Date.now() - unseenSince > 8000) {
          await this.problem("a card waits in the core but is not shown in the chat (it shows only after a reload)", "card-not-live");
          await this.page.reload();
          await expect(this.pendingCard().first(), "after a reload the waiting card is shown").toBeVisible();
          unseenSince = undefined;
        }
      } else if (!(await this.stopButton().isVisible()) && (await this.chat.getByText(MARK).count()) > marks) {
        await this.shot("brief-done");
        return answered;
      }
      await this.page.waitForTimeout(500);
    }
    await this.problem(`the Brief «${text}» did not end in time`, "brief-timeout");
    return answered;
  }

  private async answer(card: Locator): Promise<string> {
    await card.scrollIntoViewIfNeeded();
    // `card` matches only unanswered cards, so once answered it is gone: count the answers in the chat instead.
    const answers = this.chat.locator("section.border-copper").getByText(this.w.done);
    const before = await answers.count();
    let kind = "approval";
    if (await card.getByRole("checkbox").count()) {
      kind = "rows";
      await this.shot("rows-card");
      for (const box of await card.getByRole("checkbox").all()) await box.check();
      await card.getByRole("button", { name: this.w.keepTicked }).click();
    } else if (await card.locator("fieldset").count()) {
      kind = "question";
      await this.shot("question-card");
      for (const set of await card.locator("fieldset").all()) {
        const radio = set.getByRole("radio").first();
        if (await radio.count()) await radio.check();
        else await set.getByRole("textbox").fill(this.lang === "ar" ? "إجابة تجريبية" : "bench answer (sample)");
      }
      await card.getByRole("button", { name: this.w.send, exact: true }).click();
    } else {
      await this.shot("approval-card");
      const yes = card.getByRole("button", { name: this.w.yes, exact: true });
      await (await yes.count() ? yes : card.getByRole("button").first()).click();
    }
    await expect.soft(answers, `the ${kind} card shows its answer`).toHaveCount(before + 1);
    await this.shot(`${kind}-answered`);
    return kind;
  }

  /** The Deliverables made by the Brief: on the canvas live, then each opened from its chat card. */
  async deliverables(expected: number) {
    const frames = this.page.locator('[data-frame^="deliverable:"]');
    await this.page.waitForTimeout(1500);
    // The canvas draws only the frames in view: zoom out until all of them are.
    const zoomOut = this.page.getByRole("button", { name: this.w.zoomOut, exact: true });
    for (let i = 0; i < 4; i++) await zoomOut.click();
    await this.page.waitForTimeout(600);
    const live = await frames.count();
    if (live < expected) {
      await this.problem(`only ${live} of ${expected} Deliverables are on the canvas without a reload`, "deliverables-not-live");
      await this.page.reload();
      for (let i = 0; i < 4; i++) await zoomOut.click();
      await expect(frames, "after a reload every Deliverable is on the canvas").toHaveCount(expected);
    }
    await this.shot("deliverables-on-canvas");
    const opens = this.chat.getByRole("button", { name: new RegExp(`^${this.w.open}: `) });
    const count = await opens.count();
    expect.soft(count, "each Deliverable has its card in the chat").toBe(expected);
    for (let i = 0; i < count; i++) {
      await opens.nth(i).click();
      await this.page.waitForTimeout(1200);
      await this.shot(`deliverable-${i + 1}-open`);
      await this.page.keyboard.press("Escape");
      await this.page.waitForTimeout(400);
    }
  }

  /** Every problem met: console errors, failed /api requests and the soft failures, each on its own line. */
  finish() {
    expect.soft(this.problems, `problems met in the walk:\n${this.problems.join("\n")}`).toEqual([]);
  }
}

export const test = base.extend<{ walk: Walk }>({
  walk: async ({ page }, use, info) => {
    const walk = new Walk(page, info);
    await use(walk);
    walk.finish();
  },
});
export { expect };
