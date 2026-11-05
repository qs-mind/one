// The journey of a project, on the real app and core with the bench's fake AI, in Arabic and in English:
// 1. a tender folder chosen with no project open → a new project, its report, the "I understood this" card → approve;
//    old work → archived projects that offer "Understand it";
// 2. Confidential on (the code once) and off, then Close project → checklist → a lesson carried → archive → read-only;
// 3. the backup folder → Back up now → the Backup key's recovery code → on a new computer (the bench's own route),
//    restore from the folder with that code.
// Each language starts from an empty data folder. Screenshots: test-results/bench/shots, and as
// t11-NN-<state>-<ar|en>.png in $QSONE_T11_SHOTS when it is set.
import { copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fill, texts } from "../src/i18n";
import { expect, samplesDir, test, type Walk } from "./bench";

const benchDir = path.dirname(samplesDir);
const TENDER = "مناقصة عينة - منصة الاختبار"; // core/tests/bench/samples.py TENDER_NAME
const OLD = path.join(benchDir, "old", "شغل قديم - عينة"); // OLD_NAME, with OLD_PROJECTS inside
const OLD_PROJECTS = ["برج إداري - عينة قديمة", "مدرسة - عينة قديمة"];

const ORDER = [
  "drop-zone",
  "import-report",
  "understood-card",
  "fact-change",
  "understood-approved",
  "backup-ask",
  "old-work",
  "projects-archived",
  "confidential-code",
  "confidential-off",
  "close-checklist",
  "close-lessons",
  "archived-read-only",
  "backup-panel",
  "backup-done",
  "backup-recovery-code",
  "restore-found",
  "restore-done",
];

async function shot(walk: Walk, state: string) {
  const file = await walk.shot(`${state}-${walk.lang}`);
  const extra = process.env.QSONE_T11_SHOTS;
  if (extra) {
    mkdirSync(extra, { recursive: true });
    const n = String(ORDER.indexOf(state) + 1).padStart(2, "0");
    copyFileSync(file, path.join(extra, `t11-${n}-${state}-${walk.lang}.png`));
  }
}

const say = (walk: Walk, key: keyof typeof texts) => texts[key][walk.lang];

async function more(walk: Walk, item: keyof typeof texts) {
  await walk.page.locator('[data-region="topbar"]').getByRole("button", { name: say(walk, "more"), exact: true }).click();
  await walk.page.getByRole("button", { name: say(walk, item), exact: true }).click();
}

/** "Import a tender folder" or "Import old work" from More, and the folder given to the browser's chooser. */
async function chooseFolder(walk: Walk, item: "importMenu" | "readyImportOld", folder: string) {
  const chooser = walk.page.waitForEvent("filechooser");
  await more(walk, item);
  await (await chooser).setFiles(folder);
}

async function newComputer(walk: Walk) {
  // the core speaks the screen's language (an earlier walk may have left another)
  await walk.page.request.put("/api/setup/language", { data: { state: "done", lang: walk.lang } });
  const r = await walk.page.request.post("/api/bench/new-computer");
  await walk.page.evaluate(() => localStorage.removeItem("qsone.project")); // nor does the screen remember one
  expect(r.ok(), "the bench forgets this computer").toBe(true);
  await walk.page.goto("/");
  await expect(walk.page.getByRole("textbox", { name: say(walk, "message") })).toBeVisible();
}

for (const lang of ["ar", "en"] as const) {
  test(`the journey of a project (${lang})`, async ({ walk }) => {
    const page = walk.page;
    await walk.start(lang);
    await newComputer(walk); // no project and no backup folder: the first project is this one
    const backups = path.join(benchDir, `backups-${lang}`);
    mkdirSync(backups, { recursive: true });

    // 1. A tender folder, with no project open --------------------------------------------------------------
    const dt = await page.evaluateHandle(() => {
      const d = new DataTransfer();
      d.items.add(new File(["x"], "x.pdf"));
      return d;
    });
    const chat = walk.chat;
    await chat.dispatchEvent("dragenter", { dataTransfer: dt });
    await expect(page.getByText(say(walk, "importDrop"))).toBeVisible();
    await shot(walk, "drop-zone");
    await chat.dispatchEvent("dragleave", { dataTransfer: dt });

    await chooseFolder(walk, "importMenu", path.join(benchDir, "tender", TENDER));
    const top = page.locator('[data-region="topbar"]');
    await expect(top.getByRole("button", { name: TENDER })).toBeVisible();
    const report = page.locator("[data-import-report]").first();
    await expect(report.getByText(fill(say(walk, "importAdded"), { n: 4 }))).toBeVisible({ timeout: 60_000 });
    await shot(walk, "import-report");

    const kinds = await walk.follow("I understood this");
    expect.soft(kinds, "the BOQ's columns are confirmed on the way").toEqual(["rows"]);
    const card = chat.locator("[data-understood-card]");
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await shot(walk, "understood-card");

    await card.getByRole("button", { name: new RegExp(`^${say(walk, "understoodChange")}: ${say(walk, "understoodContractType")}`) }).click();
    const contract = card.getByLabel(say(walk, "understoodContractType"));
    await contract.fill(lang === "ar" ? "مقطوعية (عينة)" : "Lump sum (sample)");
    await shot(walk, "fact-change");
    await contract.press("Enter"); // no Save button: Enter (or leaving the field) saves it
    await expect(card.getByText(lang === "ar" ? "مقطوعية (عينة)" : "Lump sum (sample)")).toBeVisible();
    await card.getByRole("button", { name: say(walk, "understoodApprove"), exact: true }).click();
    await expect(chat.locator("[data-understood-card][data-approved]")).toBeVisible();
    await shot(walk, "understood-approved");

    // the first project: One asks once where to keep backups
    const ask = page.getByRole("region", { name: say(walk, "backupTitle") }).filter({ hasText: say(walk, "backupAskFolder") });
    if (await ask.isVisible()) {
      await shot(walk, "backup-ask");
      await ask.getByRole("button", { name: say(walk, "backupLater"), exact: true }).click();
    } else await walk.problem("One did not ask where to keep backups after the first project", "backup-ask-missing");
    await report.getByRole("button", { name: say(walk, "close"), exact: true }).click();

    // old work: each folder inside the one chosen is an archived project
    await chooseFolder(walk, "readyImportOld", OLD);
    const olds = page.locator("[data-import-report]");
    await expect(olds).toHaveCount(2, { timeout: 60_000 });
    for (const name of OLD_PROJECTS) await expect(olds.filter({ hasText: name }).getByText(say(walk, "importOldArchived"))).toBeVisible();
    await expect(olds.first().getByRole("button", { name: say(walk, "importUnderstandIt") })).toBeVisible();
    await expect(top.getByRole("button", { name: TENDER }), "old work does not take the engineer away").toBeVisible();
    await shot(walk, "old-work");
    for (let i = 0; i < 2; i++) await olds.first().getByRole("button", { name: say(walk, "close"), exact: true }).click();

    await top.getByRole("button", { name: TENDER }).click();
    await expect(page.getByRole("heading", { name: say(walk, "archivedGroup"), exact: true })).toBeVisible();
    await shot(walk, "projects-archived");
    await page.keyboard.press("Escape");

    // 2. Confidential, then Close project ---------------------------------------------------------------------
    await more(walk, "confidential");
    await page.getByRole("button", { name: say(walk, "confidentialTurnOn"), exact: true }).click();
    const code = page.locator("output");
    await expect(code).toHaveText(/^[A-Z0-9]{5}(-[A-Z0-9]{5})+$/);
    await shot(walk, "confidential-code");
    const last = (await code.textContent())!.split("-").at(-1)!;
    await page.getByRole("button", { name: say(walk, "recoverySaved"), exact: true }).click();
    await page.getByLabel(say(walk, "recoveryLastGroup")).fill(last);
    await expect(code).toHaveCount(0);
    await page.getByRole("button", { name: say(walk, "confidentialTurnOff"), exact: true }).click();
    await expect(page.getByText(say(walk, "confidentialOffConfirm"))).toBeVisible();
    await shot(walk, "confidential-off");
    await page.getByRole("button", { name: say(walk, "confidentialTurnOff"), exact: true }).last().click();
    await expect(page.getByRole("button", { name: say(walk, "confidentialTurnOn"), exact: true })).toBeVisible();
    await page.getByRole("button", { name: say(walk, "close"), exact: true }).first().click();

    const marks = await chat.getByText(/bench reply|رد تجريبي/).count(); // before the lessons Brief starts
    await more(walk, "closeProject");
    const closing = page.getByRole("region", { name: fill(say(walk, "closeProjectTitle"), { name: `\u2068${TENDER}\u2069` }) });
    await expect(closing.getByText(say(walk, "lessonsFinding")).or(closing.getByText(say(walk, "lessonCarry")))).toBeVisible();
    await shot(walk, "close-checklist");
    await walk.follow("lessons", { marks });
    await expect(closing.getByRole("button", { name: say(walk, "lessonCarry"), exact: true }).first()).toBeVisible({ timeout: 30_000 });
    await shot(walk, "close-lessons");
    await closing.getByRole("button", { name: say(walk, "lessonCarry"), exact: true }).first().click();
    await expect(closing.getByText(say(walk, "lessonCarried"))).toBeVisible();
    await closing.getByRole("button", { name: new RegExp(`^(${say(walk, "archiveProject")}|${say(walk, "archiveAnyway")})$`) }).click();
    await expect(closing.getByText(say(walk, "archivedReadOnly"))).toBeVisible();
    await expect(closing.getByRole("button", { name: say(walk, "unarchiveProject") })).toBeVisible();
    await expect(top.getByText(say(walk, "archivedReadOnly"))).toBeVisible();
    await shot(walk, "archived-read-only");
    await closing.getByRole("button", { name: say(walk, "close"), exact: true }).first().click();

    // 3. Backup, then restore on a new computer ---------------------------------------------------------------
    await more(walk, "backupTitle");
    const panel = page.getByRole("region", { name: say(walk, "backupTitle") });
    await panel.getByLabel(say(walk, "backupFolderPath")).fill(backups);
    await panel.getByLabel(say(walk, "backupFolderPath")).press("Enter"); // a typed folder is used on Enter
    await expect(panel.getByText(backups)).toBeVisible();
    await shot(walk, "backup-panel");
    await panel.getByRole("button", { name: say(walk, "backupNow"), exact: true }).click();
    await expect(panel.getByRole("status")).toBeVisible({ timeout: 60_000 });
    await shot(walk, "backup-done");
    await panel.getByRole("button", { name: say(walk, "backupKeyMakeCode"), exact: true }).click();
    const backupCode = (await panel.locator("output").textContent())!;
    expect(backupCode).toMatch(/^[A-Z0-9]{5}(-[A-Z0-9]{5})+$/);
    await shot(walk, "backup-recovery-code");
    await panel.getByRole("button", { name: say(walk, "recoverySaved"), exact: true }).click();
    await panel.getByLabel(say(walk, "recoveryLastGroup")).fill(backupCode.split("-").at(-1)!);
    await expect(panel.locator("output")).toHaveCount(0);

    await newComputer(walk);
    await more(walk, "backupTitle");
    await panel.getByRole("button", { name: say(walk, "restoreTitle"), exact: true }).click();
    const restore = panel.getByRole("region", { name: say(walk, "restoreTitle") });
    await restore.getByLabel(say(walk, "backupFolderPath")).fill(backups);
    await restore.getByLabel(say(walk, "backupFolderPath")).press("Enter");
    // a project's name is inside its encrypted copy: each shows unnamed until it is back
    const rows = restore.locator("li");
    await expect(rows).toHaveCount(3); // the tender and the two old projects
    for (const row of await rows.all()) await expect(row.getByText(say(walk, "restoreNeedsBackupCode"))).toBeVisible();
    await shot(walk, "restore-found");
    await rows.first().getByLabel(say(walk, "restoreCode")).fill(backupCode);
    await rows.first().getByRole("button", { name: say(walk, "restoreProject"), exact: true }).click();
    const first = (await restore.getByRole("status").first().textContent()) ?? "";
    // the code brought the Backup key to this computer: the others now need nothing, and show their names
    for (const row of await rows.all()) await expect(row.getByRole("textbox")).toHaveCount(0);
    await shot(walk, "restore-done");
    for (const name of [TENDER, ...OLD_PROJECTS].filter((n) => !first.includes(n))) {
      await rows.filter({ hasText: name }).getByRole("button", { name: say(walk, "restoreProject"), exact: true }).click();
      await expect(restore.getByText(fill(say(walk, "restoreDone"), { name }))).toBeVisible();
    }
    const listed = (await (await page.request.get("/api/projects")).json()) as { projects: { name?: string }[] };
    expect(listed.projects.map((p) => p.name).sort()).toEqual([TENDER, ...OLD_PROJECTS].sort());
  });
}
