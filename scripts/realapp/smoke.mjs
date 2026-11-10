// The real-window smoke walk: the ONE desktop window (WebKitGTK) on a virtual screen, driven only by the X server's
// mouse and keyboard, with the bench's scripted AI. A fresh first launch in Arabic (the language, who you are typed
// with real keys, AI later), then Home at three window sizes, Settings from the rail, and Home again in English.
// Usage: node scripts/realapp/smoke.mjs [shots folder]   (README.md here)
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";
import { launch } from "./realapp.mjs";

const shots = path.resolve(process.argv[2] ?? path.join(tmpdir(), "qs-mind-one-realapp-shots"));
rmSync(shots, { recursive: true, force: true });
mkdirSync(shots, { recursive: true });
const SIZES = [
  [1920, 1080],
  [1366, 768],
  [1280, 720],
];
const NAME = "مهندس"; // Arabic letters, typed on the keyboard
const POSITION = "مهندس تسعير ٢";

const results = [];
const note = (line) => {
  results.push(line);
  console.log(`  ${line}`);
};

const app = await launch({ width: 1366, height: 768, firstLaunch: true, shots });
let failed;
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
  const placeIs = (place, what) => app.waitState((s) => s.place === place, what, 30_000);

  /** Types into the field `query` with the keyboard and says whether the page got exactly that text. */
  const typeInto = async (query, text) => {
    const { ok, got } = await app.typeInto(query, text);
    note(`${ok ? "typed (real keys)" : "TYPED WRONG"}: «${text}»${ok ? "" : ` arrived as «${got}»`}`);
    return ok;
  };

  await step("first launch: language", async () => {
    await app.waitFor({ role: "heading", name: /اختار لغتك|Choose your language/ }, 30_000);
    await app.shot("welcome-language-system");
    await app.click({ role: "radio", name: "العربية" });
    await app.waitFor({ role: "heading", name: "اختار لغتك" });
    await app.shot("welcome-language-ar");
    await app.click(button("التالي"));
  });

  await step("first launch: who you are", async () => {
    await app.waitFor({ role: "heading", name: "عرّفني بنفسك" });
    const typed = [
      [{ role: "textbox", name: "الاسم الأول" }, NAME],
      [{ role: "textbox", name: "الاسم الأخير" }, "عينة"],
      [{ role: "textbox", name: "المنصب" }, POSITION],
      [{ role: "textbox", name: "الشركة" }, "شركة عينة"],
    ];
    for (const [query, text] of typed) if (!(await typeInto(query, text))) throw new Error(`«${text}» did not arrive as typed`);
    for (const [label, choice] of [
      ["نوع الجهة", "مقاول"],
      ["البلد", "مصر"],
    ]) {
      await app.click({ role: "combobox", name: label });
      await app.click({ role: "option", name: choice });
    }
    await app.shot("welcome-profile-ar");
    await app.click(button("التالي"));
  });

  await step("first launch: AI later, then Home", async () => {
    await app.waitFor({ role: "heading", name: "وصّل الذكاء الاصطناعي" });
    await app.shot("welcome-ai-ar");
    await app.click(button("وصّل بعدين"));
    await placeIs("home", "Home");
    for (const [w, h] of SIZES) {
      await app.resize(w, h);
      await app.shot(`home-ar-${w}x${h}`);
    }
    await app.resize(1366, 768);
    note("first launch walked to Home with the X server's keys and clicks");
  });

  await step("Settings from the rail, the profile shown back", async () => {
    await app.click({ role: "link", name: "الإعدادات", within: rail });
    await placeIs("settings", "Settings");
    const shown = await app.text({ role: "textbox", name: "الاسم الأول" }).catch(() => "");
    note(`My profile after first launch: «${shown.trim()}»`);
    await app.shot("settings-me-ar");
  });

  await step("English from Settings' Language and look, then Home", async () => {
    await app.click({ role: "link", name: "اللغة والمظهر" });
    await app.click({ role: "radio", name: /English/ });
    await app.waitState((s) => s.lang === "en", "English");
    await app.shot("settings-look-en");
    await app.click({ role: "link", name: "Home", within: rail });
    await placeIs("home", "Home");
    await app.shot("home-en-1366x768");
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
