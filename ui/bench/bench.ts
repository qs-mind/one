// Helpers for the bench walks: the real app with the fake AI of core/tests/bench (see playwright.bench.config.ts).
// A walk records every console error, page error and failed /api request, and fails with them at the end; problems
// found on the way (a card that only shows after a reload, a document that does not come) are soft failures with a
// screenshot, so one run lists them all. The screen is the workspace: one document (switched from its title in the top
// bar) and the chat beside it.
import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test as base, type Locator, type Page, type TestInfo } from "@playwright/test";

// the folder scripts/bench.mjs makes for this port (QSONE_BENCH_PORT), so two worktrees' benches never share samples
const benchPort = Number(process.env.QSONE_BENCH_PORT || 1442);
export const samplesDir = path.join(tmpdir(), benchPort === 1442 ? "qs-mind-one-bench" : `qs-mind-one-bench-${benchPort}`, "samples");
const shotsDir = path.join("test-results", "bench", "shots");
const MARK = /bench reply|رد تجريبي/;

type Lang = "ar" | "en";
const words = {
  ar: {
    general: "الشات العام",
    projectName: "اسم المشروع",
    newProject: "مشروع جديد",
    message: "رسالة إلى كبير مهندسي الكميات",
    send: "إرسال",
    stop: "إيقاف",
    keepTicked: "احفظ الصفوف المعلّمة",
    yes: "أيوه",
    open: "افتح",
    clientBoqReadOnly: "مستند العميل: للقراءة بس",
    notInClient: "البند ده مش موجود في مقايسة العميل",
    comments: "الملاحظات",
    projectFiles: "ملفات المشروع",
    clientBoq: "مقايسة العميل",
  },
  en: {
    general: "General chat",
    projectName: "Project name",
    newProject: "New project",
    message: "Message to the Lead QS",
    send: "Send",
    stop: "Stop",
    keepTicked: "Keep the ticked rows",
    yes: "Yes",
    open: "Open",
    clientBoqReadOnly: "The client's document: read only",
    notInClient: "Not in the client's BOQ",
    comments: "Comments",
    projectFiles: "Project files",
    clientBoq: "Client BOQ",
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

  /** The open document's region (its name is the document's title). */
  get document(): Locator {
    return this.page.locator('[data-region="document"]');
  }

  /** The document switcher: the open document's title, with its ▾, in the top bar. */
  get switcher(): Locator {
    return this.page.locator('[data-region="topbar"] h1 button[aria-haspopup="menu"]');
  }

  /** Picks a document from the switcher, by (part of) its name; false when the switcher does not list it. */
  async openDocument(name: string | RegExp): Promise<boolean> {
    await this.switcher.click();
    const item = this.page.getByRole("menu").getByRole("menuitem", { name }).first();
    if (!(await item.count())) {
      await this.page.keyboard.press("Escape");
      return false;
    }
    await item.click();
    await expect(this.page.getByRole("menu")).toHaveCount(0);
    return true;
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
    if (lang === "en") {
      // the other language is in the top bar's More
      await this.page.locator('[data-region="topbar"]').getByRole("button", { name: "أكتر", exact: true }).click();
      await this.page.getByRole("button", { name: "English", exact: true }).click();
    }
    this.lang = lang;
    await expect(this.page.getByRole("textbox", { name: this.w.message })).toBeVisible();
  }

  async createProject(name: string) {
    const top = this.page.locator('[data-region="topbar"]');
    await top.getByRole("button", { name: this.w.general }).click();
    await this.page.getByRole("button", { name: this.w.newProject }).click(); // the row turns into the name field
    await this.page.getByLabel(this.w.projectName).fill(name);
    await this.page.getByLabel(this.w.projectName).press("Enter");
    await expect(top.getByRole("button", { name })).toBeVisible();
    // a new project opens on Project files, with its drop area
    await expect(this.document).toHaveAttribute("aria-label", this.w.projectFiles);
    const list = (await (await this.page.request.get("/api/projects")).json()) as { projects: { id: string; name: string }[] };
    this.projectId = list.projects.find((p) => p.name === name)?.id;
    expect(this.projectId, "the new project is listed").toBeTruthy();
  }

  /** The sample files (and `extra` ones; only those when `samples` is false), through Project files' Add files, as the
   * engineer adds them; they show in Project files at once, without a reload. */
  async addFiles(extra: string[] = [], samples = true) {
    const files = [...(samples ? readdirSync(samplesDir).map((f) => path.join(samplesDir, f)) : []), ...extra];
    if ((await this.document.getAttribute("aria-label")) !== this.w.projectFiles) await this.openDocument(this.w.projectFiles);
    await this.document.locator('input[type="file"]').setInputFiles(files);
    for (const file of files) {
      const name = path.basename(file).replace(/\.[^.]+$/, "").slice(0, 12);
      await expect(this.document.getByText(name).first(), `${name} shows in Project files`).toBeVisible();
    }
  }

  private async waiting(): Promise<number> {
    if (!this.projectId) return 0;
    const r = await this.page.request.get(`/api/projects/${this.projectId}/status`);
    return r.ok() ? (((await r.json()) as { waiting?: number }).waiting ?? 0) : 0;
  }

  pendingCard(): Locator {
    // a card still waiting: an answered one folds to a line and says so (data-answered)
    return this.chat.locator("section[data-approval-card]:not([data-answered])").filter({ has: this.page.locator("button") });
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
    return this.follow(text, { timeout, marks });
  }

  /** Answers every card of the Brief running in the chat as it comes, until the Brief ends (its bench reply shows).
   * For a Brief One starts itself (a tender folder's, a project's lessons), `marks` is 0 in a new project. */
  async follow(what: string, { timeout = 180_000, marks = 0 } = {}): Promise<string[]> {
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
    await this.problem(`the Brief «${what}» did not end in time`, "brief-timeout");
    return answered;
  }

  async answer(card: Locator): Promise<string> {
    await card.scrollIntoViewIfNeeded();
    // `card` matches only unanswered cards, so once answered it is gone: count the answers in the chat instead.
    const answers = this.chat.locator("section[data-approval-card][data-answered]");
    const before = await answers.count();
    // the card speaks its Brief's language (its `lang`), which may not be the screen's: an English Brief in Arabic
    const said = await card.getAttribute("lang");
    const lang: Lang = said === "en" || said === "ar" ? said : this.lang;
    const w = words[lang];
    let kind = "approval";
    if (await card.getByRole("checkbox").count()) {
      kind = "rows";
      await this.shot("rows-card");
      for (const box of await card.getByRole("checkbox").all()) await box.check();
      await card.getByRole("button", { name: w.keepTicked }).click();
    } else if (await card.getByRole("combobox").count()) {
      kind = "rows"; // a BOQ's columns, each with what it holds: approved as mapped
      await this.shot("rows-card");
      const yes = card.getByRole("button", { name: w.yes, exact: true });
      await ((await yes.count()) ? yes : card.getByRole("button").first()).click();
    } else if (await card.locator("fieldset").count()) {
      kind = "question";
      await this.shot("question-card");
      for (const set of await card.locator("fieldset").all()) {
        const radio = set.getByRole("radio").first();
        if (await radio.count()) await radio.check();
        else await set.getByRole("textbox").fill(lang === "ar" ? "إجابة تجريبية" : "bench answer (sample)");
      }
      await card.getByRole("button", { name: w.send, exact: true }).click();
    } else {
      await this.shot("approval-card");
      const yes = card.getByRole("button", { name: w.yes, exact: true });
      const button = (await yes.count()) ? yes : card.getByRole("button").first();
      if ((await button.getAttribute("data-hold")) === null) await button.click();
      else {
        // paid or irreversible: the engineer holds it (about 900 ms), a click does nothing
        const box = (await button.boundingBox())!;
        await this.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await this.page.mouse.down();
        await this.page.waitForTimeout(1200);
        await this.page.mouse.up();
      }
    }
    await expect.soft(answers, `the ${kind} card shows its answer`).toHaveCount(before + 1);
    await this.shot(`${kind}-answered`);
    return kind;
  }

  /** After a BOQ import: the client's BOQ is in the document switcher at once, a read-only document, and its rows
   * show when it is picked. */
  async clientBoq(rowText: string) {
    const name = new RegExp(`^${this.w.clientBoq}`);
    if (!(await this.openDocument(name))) {
      await this.page.waitForTimeout(3000);
      if (!(await this.openDocument(name))) {
        await this.problem("the Client BOQ is not in the document switcher without a reload", "client-boq-not-live");
        await this.page.reload();
        expect(await this.openDocument(name), "the Client BOQ is in the document switcher").toBe(true);
      }
    }
    await expect.soft(this.document.getByRole("grid"), "the Client BOQ shows as a sheet").toBeVisible();
    await expect.soft(this.document.getByText(rowText).first(), "the client's rows show").toBeVisible();
    await expect.soft(this.document.getByText(this.w.clientBoqReadOnly).first(), "it says it is read only").toBeVisible();
    return this.shot("client-boq-document");
  }

  /** The Priced BOQ, opened from its card as the document, shows the Checking QS's open comment on the extra row in
   * its own review area. */
  async notInClientFlag() {
    await this.chat.getByRole("button", { name: new RegExp(`^${this.w.open}: `) }).first().click();
    await expect(this.document.getByRole("grid")).toBeVisible();
    await this.page.waitForTimeout(800);
    await this.document.getByRole("tab", { name: new RegExp(`^${this.w.comments}`) }).click();
    const flag = this.document.getByRole("tabpanel").getByText(this.w.notInClient).first();
    await expect.soft(flag, "the extra row's comment shows").toBeVisible();
    const size = this.page.viewportSize();
    await this.page.setViewportSize({ width: 1440, height: 1400 }); // the comments panel is short: a taller shot
    await flag.evaluate((e) => e.scrollIntoView({ block: "center" })).catch(() => undefined);
    const file = await this.shot("not-in-client-boq-comment");
    if (size) await this.page.setViewportSize(size);
    return file;
  }

  /** The Deliverables made by the Brief: in the document switcher live, then each opened from its chat card as the
   * document. */
  async deliverables(expected: number) {
    await this.page.waitForTimeout(1500);
    const listed = async () => {
      await this.switcher.click();
      const menu = this.page.getByRole("menu");
      await expect(menu).toBeVisible();
      const n = (await menu.getByRole("menuitem").count()) - 1 - (await menu.getByRole("menuitem", { name: new RegExp(`^${this.w.clientBoq}`) }).count());
      await this.shot("deliverables-in-switcher");
      await this.page.keyboard.press("Escape");
      return n; // less Project files and the client BOQs
    };
    const live = await listed();
    if (live < expected) {
      await this.problem(`only ${live} of ${expected} Deliverables are in the document switcher without a reload`, "deliverables-not-live");
      await this.page.reload();
      expect(await listed(), "after a reload every Deliverable is in the switcher").toBe(expected);
    }
    const opens = this.chat.getByRole("button", { name: new RegExp(`^${this.w.open}: `) });
    const count = await opens.count();
    expect.soft(count, "each Deliverable has its card in the chat").toBe(expected);
    for (let i = 0; i < count; i++) {
      const title = (await opens.nth(i).getAttribute("aria-label"))!.replace(new RegExp(`^${this.w.open}: `), "");
      await opens.nth(i).click();
      await expect.soft(this.document, "the card opens its Deliverable as the document").toHaveAttribute("aria-label", title);
      await this.page.waitForTimeout(800);
      await this.shot(`deliverable-${i + 1}-open`);
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
