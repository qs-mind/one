// The real-window tender walk (Phase 1, Wave 2): a clean data folder and a first launch in Arabic, then a synthetic
// tender folder dropped on Home (an X drag from a stand-in file manager on the same virtual screen), the BOQ's columns
// kept, the plan asked for and approved from its card, the priced sheet's stage signed off, the room opened from "the
// team now", and a spending cap changed by asking the Lead, checked in Settings. The bench's scripted AI does the
// Lead's part (core/tests/bench/tender.py); every file and name is a labelled sample.
// Usage: node scripts/realapp/tender.mjs [shots folder]   (README.md here)
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";
import { corePython, root } from "../python.mjs";
import { launch } from "./realapp.mjs";

const shots = path.resolve(process.argv[2] ?? path.join(tmpdir(), "qs-mind-one-realapp-tender-shots"));
rmSync(shots, { recursive: true, force: true });
mkdirSync(shots, { recursive: true });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const CAP = "٥٠"; // the monthly cap asked for, in Arabic-Indic digits; the Settings field shows it as 50
const ASK_CAP = `خلّي سقف الصرف الشهري ${CAP} دولار`;

// A stand-in file manager: one GTK window whose button drags the folder (text/uri-list), as a file manager's does.
const DRAG_SOURCE = `import sys
from pathlib import Path
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
folder = Path(sys.argv[1])
window = Gtk.Window(title="sample-folder-source")
window.set_default_size(300, 120)
window.move(int(sys.argv[2]), 40)
button = Gtk.Button(label=folder.name)
button.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
button.drag_source_add_uri_targets()
button.connect("drag-data-get", lambda w, ctx, data, info, t: data.set_uris([folder.as_uri()]))
window.add(button)
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
`;

const results = [];
const note = (line) => {
  results.push(line);
  console.log(`  ${line}`);
};

const app = await launch({ width: 1366, height: 768, firstLaunch: true, shots });
let failed;
let source;
try {
  const button = (name, extra = {}) => ({ role: "button", name, exact: true, ...extra });
  const rail = { css: "nav" };
  const step = async (what, fn) => {
    console.log(`- ${what}`);
    try {
      await fn();
    } catch (error) {
      await app.shot(`failed-${what.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`, { screen: true }).catch(() => {});
      throw new Error(`${what}: ${error.message}`);
    }
  };
  const placeIs = (place, what, timeout = 30_000) => app.waitState((s) => s.place === place, what, timeout);
  const typeInto = async (query, text) => {
    const { ok, got } = await app.typeInto(query, text);
    if (!ok) throw new Error(`«${text}» arrived as «${got}»`);
  };
  /** A press held past the HoldButton's 900 ms, as a person approves paid work. */
  const hold = async (query) => {
    await app.waitFor(query, 60_000);
    await app.waitStill();
    // the thread follows a reply still coming in: hold only once the button stays where it is
    let p = await app.point(query);
    for (let still = 0, i = 0; still < 4 && i < 100; i++) {
      await sleep(250);
      const now = await app.point(query);
      still = now.x === p.x && now.y === p.y ? still + 1 : 0;
      p = now;
    }
    app.focus();
    app.xdo("mousemove", "--sync", p.x, p.y);
    app.xdo("mousedown", 1);
    await sleep(1400);
    app.xdo("mouseup", 1);
    await sleep(300);
  };
  const waitingItem = (kind) => ({ css: `[data-waiting="${kind}"] button` });

  await step("first launch: language, who you are, AI agreed", async () => {
    await app.waitFor({ role: "heading", name: /اختار لغتك|Choose your language/ }, 30_000);
    await app.click({ role: "radio", name: "العربية" });
    await app.waitFor({ role: "heading", name: "اختار لغتك" });
    await app.click(button("التالي"));
    await app.waitFor({ role: "heading", name: "عرّفني بنفسك" });
    for (const [label, text] of [
      ["الاسم الأول", "مهندس"],
      ["الاسم الأخير", "عينة"],
      ["المنصب", "مهندس تسعير - عينة"],
      ["الشركة", "شركة عينة"],
    ])
      await typeInto({ role: "textbox", name: label }, text);
    for (const [label, choice] of [
      ["نوع الجهة", "مقاول"],
      ["البلد", "مصر"],
    ]) {
      await app.click({ role: "combobox", name: label });
      await app.click({ role: "option", name: choice });
    }
    await app.shot("welcome-profile");
    await app.click(button("التالي"));
    await app.waitFor({ role: "heading", name: "وصّل الذكاء الاصطناعي" });
    await app.click(button("موافق")); // the AI note; the bench's own models are connected already
    await app.waitFor({ text: /^وافقت\./ });
    await app.shot("welcome-ai-agreed");
    // the bench's own models are connected already: step 3 says so and offers Start
    await app.waitFor({ text: "فيه ذكاء اصطناعي متوصّل خلاص. تقدر تبدأ." });
    await app.click(button("ابدأ"));
    await placeIs("home", "Home");
    await app.shot("home-first");
    note("first launch walked to Home in Arabic, the AI note agreed");
  });

  await step("drop a synthetic tender folder on Home", async () => {
    const made = path.join(app.dir, "sample-tender");
    const code = `from pathlib import Path; from tests.bench import samples; print(samples.write_walk(Path(${JSON.stringify(made)})))`;
    const folder = execFileSync(corePython(), ["-c", code], { cwd: path.join(root, "core"), encoding: "utf8" }).trim();
    const script = path.join(app.dir, "dragsource.py");
    writeFileSync(script, DRAG_SOURCE);
    // on our X display only, never the engineer's own (Wayland) screen
    const env = { ...app.env, GDK_BACKEND: "x11", NO_AT_BRIDGE: "1" };
    delete env.WAYLAND_DISPLAY;
    const log = path.join(app.dir, "dragsource.log");
    source = spawn("sh", ["-c", `exec python3 "$0" "$1" 1500 >"$2" 2>&1`, script, folder, log], { env });
    const id = await (async () => {
      for (let i = 0; i < 50; i++, await sleep(200)) {
        const found = app.findWindows().find((w) => w !== app.window);
        if (found) return found;
      }
      throw new Error(`the stand-in file manager did not open; see ${log}`);
    })();
    await sleep(500);
    await app.shot("drop-before", { screen: true });
    const from = app.geometry(id);
    const a = { x: from.x + Math.round(from.width / 2), y: from.y + Math.round(from.height / 2) };
    const b = await app.point({ role: "textbox", name: "رسالة للـ Lead QS" });
    app.xdo("mousemove", "--sync", a.x, a.y);
    app.xdo("mousedown", 1);
    for (let i = 1; i <= 30; i++) {
      app.xdo("mousemove", "--sync", Math.round(a.x + ((b.x - a.x) * i) / 30), Math.round(a.y + ((b.y - a.y) * i) / 30));
      await sleep(40);
    }
    await sleep(400);
    await app.shot("drop-over-home", { screen: true });
    app.xdo("mouseup", 1);
    await placeIs("tender", "the dropped folder to open as a tender", 30_000);
    await app.waitFor({ role: "heading", name: /مناقصة عينة - مشي النافذة/ }, 30_000);
    await app.shot("tender-opened");
    note("the folder dropped on Home opened as its tender");
  });

  await step("keep the BOQ's columns", async () => {
    await app.click(waitingItem("rows"), { timeout: 90_000 });
    await app.shot("rows-waiting");
    await app.click({ role: "button", name: /احفظ/ }, { timeout: 15_000 });
    await app.waitGone(waitingItem("rows"), 30_000);
    note("the BOQ's columns were kept from the tender");
  });

  await step("ask for the plan and approve it from its card", async () => {
    await app.click(button("اطلب من الـ Lead QS يكتب الخطة"), { timeout: 90_000 });
    await app.waitFor({ text: "خطة التندر" }, 90_000);
    await app.shot("plan-card");
    await hold(button("وافق وابدأ"));
    await app.waitFor({ text: /^اتوافق عليها/ }, 30_000);
    await app.shot("plan-approved");
    note("the plan was approved from its card (held)");
  });

  await step("sign off the stage with the priced sheet", async () => {
    await app.waitFor({ css: '[data-stage][data-state="waiting"]' }, 180_000);
    await app.shot("stage-waits");
    await app.click(waitingItem("stage"));
    await app.click({ role: "button", name: /اعتمد|وقّع/ }, { timeout: 15_000 });
    await app.waitFor({ css: '[data-stage][data-state="done"]' }, 30_000);
    await app.shot("stage-signed-off");
    note("the stage was signed off with its priced sheet");
  });

  await step("open the room from the team now", async () => {
    await app.click({ role: "link", name: "افتح غرفة الفريق" });
    await app.waitState((s) => /\/room$/.test(s.url), "the room", 15_000);
    await app.waitFor({ text: /بدأت في أسعار العينة/ }, 15_000);
    await app.shot("room");
    note("the room shows the member's message to the Lead");
  });

  await step("ask the Lead to change the monthly cap, then see it in Settings", async () => {
    // the tender's thread stays beside the room, with its own message box
    await typeInto({ role: "textbox", name: "رسالة للـ Lead QS" }, ASK_CAP);
    await app.key("Return");
    await app.waitFor({ text: /بيغيّر إعداد/ }, 60_000);
    await app.shot("cap-asked");
    await app.click({ role: "link", name: "الإعدادات", within: rail });
    await placeIs("settings", "Settings");
    await app.click({ role: "link", name: "حدود الصرف" });
    const field = { role: "textbox", name: /الشهر الواحد/ };
    await app.waitFor(field);
    const shown = (await app.text(field)).trim();
    await app.shot("settings-caps");
    if (shown !== "50") throw new Error(`the month cap shows «${shown}», not 50`);
    note(`the Lead changed the monthly cap: Settings shows «${shown}»`);
  });
} catch (error) {
  failed = error;
} finally {
  source?.kill();
  await app.stop();
}

console.log(`\nShots: ${shots}`);
console.log(`Logs: ${JSON.stringify(app.logs())}`);
if (failed) {
  console.error(`\nFAILED: ${failed.message}`);
  process.exit(1);
}
console.log(`\nPassed:\n${results.map((r) => `  ${r}`).join("\n")}`);
