// The real-window smoke walk: the ONE desktop window (WebKitGTK) on a virtual screen, driven only by the X server's
// mouse and keyboard, with the bench's scripted AI. A fresh first launch in Arabic, a new project and its drop area,
// Choose files through GTK's own file dialog, the BOQ opened and zoomed, screenshots at three window sizes in Arabic
// and English, full screen (Ctrl+Shift+F), and an Arabic message typed and sent in the chat.
// Usage: node scripts/realapp/smoke.mjs [shots folder]   (README.md here)
import { existsSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";
import { launch } from "./realapp.mjs";
import { root } from "./build.mjs";

const shots = path.resolve(process.argv[2] ?? path.join(tmpdir(), "qs-mind-one-realapp-shots"));
rmSync(shots, { recursive: true, force: true });
mkdirSync(shots, { recursive: true });
const BOQ = boq();
/** The priced BOQ of docs/test-files (the private docs repo, cloned in the main checkout only; a worktree finds it
 * there through its .git file), or $QSONE_REALAPP_BOQ. */
function boq() {
  if (process.env.QSONE_REALAPP_BOQ) return process.env.QSONE_REALAPP_BOQ;
  const rel = path.join("docs", "test-files", "egypt", "lahun-medical-center", "boq-priced.xlsx");
  const candidates = [path.join(root, rel)];
  const dotGit = path.join(root, ".git");
  if (existsSync(dotGit) && !statSync(dotGit).isDirectory()) {
    const gitdir = /gitdir: (.+)/.exec(readFileSync(dotGit, "utf8"))?.[1]?.trim(); // <main>/.git/worktrees/<name>
    if (gitdir) candidates.push(path.join(path.resolve(gitdir, "..", "..", ".."), rel));
  }
  const found = candidates.find((file) => existsSync(file));
  if (!found) throw new Error(`no ${rel}: clone the docs repo, or set QSONE_REALAPP_BOQ`);
  return found;
}
const SIZES = [
  [1920, 1080],
  [1366, 768],
  [1280, 720],
];
const PROJECT = "مستشفى اللاهون ٢٠٢٦"; // Arabic letters and Arabic-Indic digits, typed on the keyboard
const MESSAGE = "راجع بنود الخرسانة في المقايسة وقولي إجمالي البند ٠٢/٠٣ كام؟";
const MARK = /bench reply|رد تجريبي/;

const results = [];
const note = (line) => {
  results.push(line);
  console.log(`  ${line}`);
};

const app = await launch({ width: 1366, height: 768, firstLaunch: true, shots });
let failed;
try {
  const button = (name, extra = {}) => ({ role: "button", name, exact: true, ...extra });
  const top = { css: "[data-region='topbar']" };
  const step = async (what, fn) => {
    console.log(`- ${what}`);
    try {
      await fn();
    } catch (error) {
      await app.shot(`failed-${what.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`, { screen: true }).catch(() => {});
      throw new Error(`${what}: ${error.message}`);
    }
  };

  const waitWidth = async (query, ok, what) => {
    for (let i = 0; i < 50; i++) {
      const { width } = await app.rect(query);
      if (ok(width)) return width;
      await new Promise((r) => setTimeout(r, 150));
    }
    throw new Error(`timed out waiting for ${what}`);
  };

  /** Types into the field `query` with the keyboard and says whether the page got exactly that text. */
  const typeInto = async (query, text) => {
    const { ok, got } = await app.typeInto(query, text);
    note(`${ok ? "typed (real keys)" : "TYPED WRONG"}: «${text}»${ok ? "" : ` arrived as «${got}»`}`);
    return ok;
  };

  await step("first launch: language", async () => {
    await app.waitFor({ role: "heading", name: /اختار لغتك|Choose your language/ }, 30_000);
    await app.shot("setup-language-system");
    await app.click(button("العربية"));
    await app.waitFor({ role: "heading", name: "اختار لغتك" });
    await app.shot("setup-language-ar");
    await app.click(button("التالي"));
  });
  await step("first launch: account, AI, card, usage, ready", async () => {
    await app.waitFor({ role: "heading", name: "حساب QS Mind بتاعك" });
    await app.click(button("تخطّى"));
    await app.waitFor({ role: "heading", name: "وصّل الذكاء الاصطناعي" });
    await app.click(button("فهمت"));
    await app.click({ role: "button", name: /^مفتاح API/ });
    await app.shot("setup-ai-ar");
    await app.click(button("تخطّى"));
    await app.waitFor({ role: "heading", name: "بطاقة التعريف" });
    await app.click({ role: "radio", name: "مهندس كميات عند مقاول" });
    await typeInto({ role: "textbox", name: "المدينة" }, "القاهرة");
    await app.shot("setup-card-ar");
    await app.click(button("التالي"));
    await app.waitFor({ role: "heading", name: "إحصائيات الاستخدام" });
    await app.click(button("ماتشاركش"));
    await app.waitFor({ role: "heading", name: "ONE جاهز" });
    await app.shot("setup-ready-ar");
    await app.click(button("ابدأ من غير فولدر"));
    await app.waitFor({ role: "textbox", name: "رسالة إلى كبير مهندسي الكميات" });
    await app.shot("app-ar");
  });

  await step("new project, its drop area", async () => {
    await app.click({ role: "button", name: "الشات العام", within: top });
    await app.click(button("مشروع جديد"));
    await typeInto({ role: "textbox", name: "اسم المشروع" }, PROJECT);
    await app.key("Return");
    await app.waitFor({ role: "button", name: /مستشفى اللاهون/, within: top });
    const shown = await app.text({ role: "button", name: /مستشفى اللاهون/, within: top });
    note(`the project's name in the top bar: «${shown.trim()}»${shown.includes(PROJECT) ? "" : " (not as typed)"}`);
    await app.waitFor({ css: "[data-empty-drop]" });
    const s = await app.state();
    if (s.document !== "ملفات المشروع") throw new Error(`the new project opened on «${s.document}», not Project files`);
    for (const [w, h] of SIZES) {
      await app.resize(w, h);
      await app.shot(`empty-ar-${w}x${h}`);
    }
    await app.resize(1366, 768);
  });

  await step("Choose files, through GTK's file dialog", async () => {
    const copy = app.scratchCopy(BOQ);
    const before = Date.now();
    await app.click(button("اختار ملفات"));
    await app.waitWindow();
    await new Promise((r) => setTimeout(r, 800));
    await app.shot("file-dialog", { screen: true });
    await app.chooseFiles(null, [copy]);
    await app.waitFor({ role: "button", name: "boq-priced", within: { css: "[data-region='document']" } }, 60_000);
    note(`file chosen in the GTK dialog and listed in Project files after ${((Date.now() - before) / 1000).toFixed(1)} s`);
    await app.shot("project-files-ar");
  });

  await step("open the BOQ, zoom in with Ctrl+=", async () => {
    await app.click({ role: "button", name: "boq-priced", within: { css: "[data-region='document']" } });
    await app.waitState((s) => s.document && s.document !== "ملفات المشروع", "the BOQ to open", 30_000);
    await new Promise((r) => setTimeout(r, 1500));
    const before = await app.state();
    await app.click({ css: "[data-region='document']" }, { settle: 200 }); // the document, not a field, has the keys
    await app.key("ctrl+equal");
    const after = await app.waitState((s) => s.zoom > before.zoom, "the zoom to step up");
    note(`Ctrl+= zoom: ${before.zoom} → ${after.zoom}, root font ${before.rootFontSize} → ${after.rootFontSize} px; open: «${after.document}»`);
  });

  for (const lang of ["ar", "en"]) {
    await step(`BOQ screenshots in ${lang}`, async () => {
      if (lang === "en") {
        await app.click({ role: "button", name: "أكتر", exact: true, within: top });
        await app.click(button("English"));
        await app.waitState((s) => s.lang === "en", "English");
        await new Promise((r) => setTimeout(r, 500));
      }
      for (const [w, h] of SIZES) {
        await app.resize(w, h);
        await app.shot(`boq-${lang}-${w}x${h}-zoom110`);
      }
    });
  }

  await step("Ctrl+Shift+F full screen, then back", async () => {
    await app.resize(1366, 768);
    const doc = { css: "[data-region='document']" };
    await app.click(doc, { settle: 200 });
    const narrow = (await app.rect(doc)).width;
    await app.key("ctrl+shift+f");
    const wide = await waitWidth(doc, (w) => w > narrow + 100, "the document to take the chat's room");
    await app.shot("full-screen-en");
    await app.key("ctrl+shift+f");
    await waitWidth(doc, (w) => w < wide - 100, "the chat to come back");
    note(`Ctrl+Shift+F: the document ${Math.round(narrow)} → ${Math.round(wide)} px wide, and back`);
  });

  await step("an Arabic message, typed and sent", async () => {
    await app.click({ role: "button", name: "More", exact: true, within: top });
    await app.click(button("العربية"));
    await app.waitState((s) => s.lang === "ar", "Arabic");
    const box = { role: "textbox", name: "رسالة إلى كبير مهندسي الكميات" };
    await app.waitFor(box);
    app.startVideo("chat-ar"); // this flow on video too: the keys arriving one by one, the reply streaming
    const real = await typeInto(box, MESSAGE);
    await app.shot("chat-typed-ar");
    if (!real) throw new Error("the message did not arrive as typed");
    await app.key("Return");
    await app.waitFor({ text: MESSAGE.slice(0, 20), within: { css: "[data-region='chat']" } }, 15_000);
    // the scripted Lead QS answers: its reply, or a card that asks first (the Brief goes on once it is answered)
    const chat = { css: "[data-region='chat']" };
    const replied = async () => (await app.visible({ text: MARK, within: chat })) || (await app.visible({ css: "[data-region='chat'] section[data-approval-card]" }));
    for (let i = 0; i < 400 && !(await replied()); i++) await new Promise((r) => setTimeout(r, 300));
    if (!(await replied())) throw new Error("the Lead QS did not answer");
    await new Promise((r) => setTimeout(r, 1000));
    await app.shot("chat-replied-ar");
    note(`the Arabic message was sent with Enter and the scripted Lead QS answered (video: ${await app.stopVideo()})`);
  });

  // what the engine draws with: fonts and sizes, for the comparison with Chromium
  const fonts = await app.ask("fonts", undefined).catch(() => undefined);
  if (fonts) note(`fonts: ${JSON.stringify(fonts)}`);
} catch (error) {
  failed = error;
} finally {
  await app.stop();
}

console.log(`\nShots: ${shots}`);
console.log(`Logs: ${JSON.stringify(app.logs())}`);
if (failed) {
  console.error(`\nFAILED: ${failed.message}`);
  process.exit(1);
}
console.log(`\nPassed:\n${results.map((r) => `  ${r}`).join("\n")}`);
