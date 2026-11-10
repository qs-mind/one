# Real-window walks

The bench walks (`ui/bench`) run in Playwright's Chromium. The ONE people install is a Tauri 2 window on WebKitGTK:
another engine, another font stack, GTK's own scrollbars and file dialog. These scripts drive **that window**, like a
person: every click, key and wheel turn is the X server's (xdotool), on a virtual screen (Xvfb), so your own screen
and keyboard stay free. Linux only.

```sh
node scripts/realapp/smoke.mjs [shots folder]   # the smoke walk; shots default to <tmp>/qs-mind-one-realapp-shots
node scripts/realapp/build.mjs [port]           # only the build (the walk builds when it needs to)
```

Needs: `Xvfb`, `xdotool`, ImageMagick (`import`), `ffmpeg` (video only), `dbus-run-session`, `python3`, the core's
`core/.venv`, `node_modules`, and Rust for the desktop crate. The smoke walk goes through first launch (the language, who
you are typed in Arabic with real keys, AI later) to Home, then Settings, and Home again in English.

## What it starts, and what it never touches

- **Screen:** its own Xvfb display (`:97` or the next free one), 1920×1080 or larger. Xvfb's screen cannot grow later.
- **Core:** the bench's (`vite.bench.config.ts` through `vite.realapp.config.ts`): a fresh data folder in
  `<tmp>/qs-mind-one-realapp-<port>`, the scripted AI, the key store in memory. Never a real AI key.
- **Vite:** port 1477 or the next free one, never 1440 (your dev app), 1442, 1702 or 18301.
- **Window:** the desktop crate built by `build.mjs` with its own identifier (`app.qsmind.one.realapp`) and its own
  target folder (`desktop/target/realapp`), so it never hands over to your ONE (single-instance), never reads your
  window state, never rebuilds your `tauri dev` binary. It runs in its own D-Bus session with no services (no portal
  could open a dialog on your screen, no key ring), with no Wayland display, and its own `XDG_DATA_HOME` (web storage,
  GTK's recent files) with your fonts linked in.
- **Real AI** (`launch({ core: "real", dir })`): the real core with real providers instead (`realcore.py`), in the
  same throw-away data folder, with keyring's fail backend (its keys in that folder's `keystore.json`, never the
  system key store), the engineer's Claude Code never found and no browser. Type the key in through the screen.
- **Step by step** (`drive.mjs`): `start '<launch options>'` keeps one window open; `send <run folder> '<step>'` runs
  one async step there with `app`, `snap`, `chat`, `api` and `stop` in scope, for walks that follow what the AI said.
- `stop()` ends only what it started; logs (`app.log`, `vite.log`, `core.log`, `xvfb.log`) stay in the run folder.

## Writing a walk

```js
import { launch } from "./realapp.mjs";
const app = await launch({ width: 1366, height: 768, firstLaunch: true, shots: "/tmp/shots" });
try {
  await app.click({ role: "button", name: "العربية", exact: true });
  await app.typeInto({ role: "textbox", name: "المدينة" }, "القاهرة"); // { ok, got }
  await app.key("ctrl+equal");
  await app.chooseFiles({ role: "button", name: "اختار ملفات" }, ["/tmp/x/boq.xlsx"]);
  await app.resize(1280, 720);
  await app.shot("boq-1280");
} finally {
  await app.stop();
}
```

Queries: `{ role, name, exact }`, `{ text }` (or a plain string), `{ testId }`, `{ css }`, with `within` and `nth`; a
name or text may be a RegExp. The page answers them through a **dev-only bridge** (`ui/src/testbridge.ts`): only a dev
server started with `VITE_QSONE_TEST_BRIDGE=1` loads it, it connects to the driver on 127.0.0.1 with a one-run token,
and it only says where things are and what they say (`rect`, `text`, `visible`, `count`, `style`, `hasFocus`,
`scrollIntoView`, `state`, `fonts`, `frames`). It never clicks or types. A production build has none of it:
`scripts/realapp/bridge.test.mjs` builds one, with the bridge's variables set, and looks.

Input: `click`, `move`, `type`, `typeInto`, `key`, `scroll`, `drag`, `resize`, `chooseFiles`; waits: `waitFor`,
`waitGone`, `waitState`, `waitStill`, `waitWindow`; output: `shot` (the window, or `{ screen: true }`), `startVideo` /
`stopVideo`.

## Things learnt on the way

- **Arabic is typed with real keys.** xdotool alone relabels one spare key for each character it has no key for, and
  under load the window reads a key after it was relabelled («راجع» arrived as «رججع»). `type` first puts every
  such character on a key of its own for the run (`keymap.py`), so xdotool only presses keys. Arabic letters,
  Arabic-Indic digits and «؟» all arrive as typed; `typeInto` checks the field and waits for a slow window.
- **A click during a view transition is lost** (the language switch's wipe): `click` waits for the field to show and
  the page to stand still, and `typeInto` checks the cursor landed.
- **Compositing stays on.** With `WEBKIT_DISABLE_COMPOSITING_MODE=1` (`launch({ compositing: false })`) the language
  switch freezes the page: it stops painting and answering.
- **GTK's file dialog takes one typed path**; several files take one dialog each (`chooseFiles(..., { again })`).
- In a worktree whose `node_modules` links to the main checkout, Vite refused to serve the fonts and every shot had
  the system's type: `vite.realapp.config.ts` allows that folder.
