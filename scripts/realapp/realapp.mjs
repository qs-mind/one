// Drives the real ONE desktop window (Tauri 2 on WebKitGTK) like a person, on a virtual screen: Xvfb for the screen,
// xdotool for every click and key, ImageMagick for screenshots. The founder's own screen, keyboard, ONE, data and key
// store are never touched: its own X display, its own D-Bus session, its own app identifier (build.mjs), and the
// bench's core (scripts/bench.mjs: a throwaway data folder, the fake AI, the key store in memory).
// The page tells the driver where things are through a dev-only bridge (ui/src/testbridge.ts); it never clicks.
// See README.md here.
import { execFileSync, spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, openSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { build, DEFAULT_PORT, IDENTIFIER, root } from "./build.mjs";
import { serve } from "./ws.mjs";

const RESERVED = new Set([1440, 1442, 1702, 18301]); // the founder's dev app, the bench, another test agent's ONE
const FIRST_LAUNCH = ["setup", "setup_done_at", "ai_consent", "usage_stats", "language"];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const BUS_CONFIG = `<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=/tmp</listen>
  <auth>EXTERNAL</auth>
  <policy context="default"><allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/><allow own="*"/></policy>
</busconfig>
`;

function portFree(port) {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.once("error", () => resolve(false));
    probe.listen(port, "127.0.0.1", () => probe.close(() => resolve(true)));
  });
}

async function freePort(from) {
  for (let port = from; port < from + 200; port++) if (!RESERVED.has(port) && (await portFree(port))) return port;
  throw new Error(`no free port from ${from}`);
}

function freeDisplay(from = 97) {
  for (let n = from; n < from + 100; n++) if (!existsSync(`/tmp/.X11-unix/X${n}`) && !existsSync(`/tmp/.X${n}-lock`)) return n;
  throw new Error("no free X display");
}

async function until(what, check, timeout = 30_000, every = 200) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) {
      last = error;
    }
    await sleep(every);
  }
  throw new Error(`timed out waiting for ${what}${last ? `: ${last.message}` : ""}`);
}

/** Stops a process group we started: TERM, then KILL if it is still there. */
async function stopGroup(child, grace = 4000) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
  const gone = new Promise((resolve) => child.once("exit", resolve));
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    return;
  }
  if (await Promise.race([gone.then(() => true), sleep(grace).then(() => false)])) return;
  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    // already gone
  }
}

/** A query for the bridge: `{ role, name }`, `{ text }`, `{ testId }`, `{ css }`, with `within` and `nth`. A RegExp
 * name or text travels as `{ re, flags }`. A plain string is text. */
function wire(query) {
  if (typeof query === "string") query = { text: query };
  const out = { ...query };
  for (const key of ["name", "text"]) if (out[key] instanceof RegExp) out[key] = { re: out[key].source, flags: out[key].flags };
  if (out.within) out.within = wire(out.within);
  return out;
}

export class RealApp {
  constructor(opts) {
    this.opts = opts;
    this.children = [];
    this.pending = new Map();
    this.nextId = 1;
    this.keys = new Set(); // characters put on spare keys (type)
    this.shotsDir = opts.shots ?? path.join(tmpdir(), "qs-mind-one-realapp-shots");
    this.n = 0;
  }

  get env() {
    return { ...process.env, DISPLAY: `:${this.display}` };
  }

  /** xdotool on our display; its output, trimmed. */
  xdo(...args) {
    return execFileSync("xdotool", args.map(String), { env: this.env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
  }

  // ---- start and stop ----

  async start() {
    const { width = 1920, height = 1080 } = this.opts;
    this.display = this.opts.display ?? freeDisplay();
    this.port = this.opts.port ?? (await freePort(DEFAULT_PORT));
    this.dir = this.opts.dir ?? path.join(tmpdir(), `qs-mind-one-realapp-${this.port}`);
    if (!this.opts.keep) rmSync(this.dir, { recursive: true, force: true });
    mkdirSync(this.dir, { recursive: true });
    mkdirSync(this.shotsDir, { recursive: true });
    const log = (name) => openSync(path.join(this.dir, name), "a");
    process.once("exit", () => this.killNow());
    for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => void this.stop().then(() => process.exit(130)));

    // the binary first: a build must not run while the screen and servers wait
    this.binary = build(this.port, { quiet: !this.opts.verbose });

    // Xvfb's screen cannot grow later (no RandR sizes), so it starts as large as any window the walk asks for
    const screen = this.opts.screen ?? { width: Math.max(width, 1920), height: Math.max(height, 1080) };
    const xvfb = spawn("Xvfb", [`:${this.display}`, "-screen", "0", `${screen.width}x${screen.height}x24`, "-nolisten", "tcp", "-noreset"], {
      stdio: ["ignore", log("xvfb.log"), log("xvfb.log")],
      detached: true,
    });
    this.children.push(xvfb);
    await until("Xvfb", () => existsSync(`/tmp/.X11-unix/X${this.display}`), 15_000);
    this.screen = screen;

    // the bridge's server, then the bench's Vite and core with the bridge turned on
    this.bridge = await serve((client) => {
      this.socket = client;
      client.onMessage = (text) => {
        const message = JSON.parse(text);
        if (message.hello) {
          this.hello = message.state;
          this.onHello?.();
          return;
        }
        const waiting = this.pending.get(message.id);
        if (!waiting) return;
        this.pending.delete(message.id);
        if (message.ok) waiting.resolve(message.value);
        else waiting.reject(new Error(message.error));
      };
      client.onClose = () => {
        if (this.socket === client) this.socket = undefined;
      };
    });
    const vite = spawn(process.execPath, [path.join(root, "node_modules", "vite", "bin", "vite.js"), "--config", path.join("scripts", "realapp", "vite.realapp.config.ts")], {
      cwd: root,
      env: {
        ...process.env,
        QSONE_BENCH_DIR: this.dir,
        QSONE_BENCH_PORT: String(this.port),
        PYTHONPATH: [path.join(root, "core"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
        ...(this.opts.core === "real" ? { QSONE_REALAPP_CORE: "real" } : {}), // realcore.py, real AI providers
        VITE_QSONE_TEST_BRIDGE: "1",
        VITE_QSONE_TEST_BRIDGE_URL: this.bridge.url,
      },
      stdio: ["ignore", log("vite.log"), log("vite.log")],
      detached: true,
    });
    this.children.push(vite);
    this.vite = vite;
    await until(this.opts.core === "real" ? "the core" : "the bench core", async () => {
      if (vite.exitCode !== null) throw new Error(`Vite stopped; see ${path.join(this.dir, "vite.log")}`);
      return (await fetch(`http://127.0.0.1:${this.port}/api/health`)).ok;
    }, 90_000, 500).catch((error) => {
      throw vite.exitCode !== null ? new Error(`Vite stopped; see ${path.join(this.dir, "vite.log")}`) : error;
    });
    if (this.opts.firstLaunch && this.opts.core !== "real") this.forgetFirstLaunch(); // a real core's fresh folder has none

    // the window: its own profile (identifier), its own D-Bus session (no single-instance hand-over, no portal)
    if (!this.opts.keepProfile) this.freshProfile();
    const env = { ...this.env, GDK_BACKEND: "x11", XDG_SESSION_TYPE: "x11", GTK_USE_PORTAL: "0", NO_AT_BRIDGE: "1" };
    // WebKit composites as on the engineer's computer; without it (compositing: false) a view transition freezes the page
    if (this.opts.compositing === false) env.WEBKIT_DISABLE_COMPOSITING_MODE = "1";
    env.WAYLAND_DISPLAY = path.join(this.dir, "no-wayland"); // nothing may find the founder's compositor
    for (const name of ["DBUS_SESSION_BUS_ADDRESS", "GNOME_KEYRING_CONTROL", "SSH_AUTH_SOCK"]) delete env[name];
    // its own data folder: the web view's storage, and GTK's recent files (the file dialog neither shows nor adds to
    // the founder's), with the founder's own fonts linked in so the type is what his ONE draws with
    env.XDG_DATA_HOME = path.join(this.dir, "xdg-data");
    mkdirSync(env.XDG_DATA_HOME, { recursive: true });
    const fonts = path.join(process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share"), "fonts");
    if (existsSync(fonts) && !existsSync(path.join(env.XDG_DATA_HOME, "fonts"))) symlinkSync(fonts, path.join(env.XDG_DATA_HOME, "fonts"));
    // a bus with no services to start: no portal (it would open on the founder's screen), no key ring, no a11y bus
    const bus = path.join(this.dir, "dbus.conf");
    writeFileSync(bus, BUS_CONFIG);
    const app = spawn("dbus-run-session", [`--config-file=${bus}`, "--", this.binary], { cwd: root, env, stdio: ["ignore", log("app.log"), log("app.log")], detached: true });
    this.children.push(app);
    this.app = app;

    const appLog = path.join(this.dir, "app.log");
    this.window = await until("the ONE window", () => {
      if (app.exitCode !== null) throw new Error(`the window's process stopped; see ${appLog}`);
      return this.findWindows()[0];
    }, 60_000, 300);
    await until("the page bridge", () => this.socket && this.hello, 60_000, 200);
    this.xdo("windowmove", this.window, 0, 0);
    await this.resize(width, height);
    this.focus();
    return this;
  }

  /** Visible windows of our display, the largest first (the main window, then a dialog or a menu). */
  findWindows() {
    let ids;
    try {
      ids = this.xdo("search", "--onlyvisible", "--name", ".").split("\n").filter(Boolean);
    } catch {
      return [];
    }
    const sized = ids.map((id) => ({ id, ...this.geometry(id) })).filter((w) => w.width > 50 && w.height > 50);
    return sized.sort((a, b) => b.width * b.height - a.width * a.height).map((w) => w.id);
  }

  geometry(id = this.window) {
    const out = Object.fromEntries(
      this.xdo("getwindowgeometry", "--shell", id)
        .split("\n")
        .map((line) => line.split("="))
        .map(([k, v]) => [k.toLowerCase(), Number(v)]),
    );
    return { x: out.x, y: out.y, width: out.width, height: out.height };
  }

  /** The bench's settings.json without the first launch's answers (as ui/bench/first-launch.spec.ts). */
  forgetFirstLaunch() {
    const file = path.join(this.dir, "data", "settings.json");
    const saved = JSON.parse(readFileSync(file, "utf8"));
    for (const key of FIRST_LAUNCH) delete saved[key];
    writeFileSync(file, JSON.stringify(saved));
  }

  /** This build's own window state and web storage (named by its identifier, never the founder's ONE). */
  freshProfile() {
    if (IDENTIFIER === "app.qsmind.one") throw new Error("refusing to clear the real ONE's profile");
    const home = homedir();
    const bases = [process.env.XDG_CONFIG_HOME || path.join(home, ".config"), process.env.XDG_DATA_HOME || path.join(home, ".local", "share"), process.env.XDG_CACHE_HOME || path.join(home, ".cache")];
    for (const base of bases) rmSync(path.join(base, IDENTIFIER), { recursive: true, force: true });
  }

  /** Closes the window, the servers and the screen we started, and nothing else. */
  async stop() {
    if (this.recording) await this.stopVideo();
    for (const child of [...this.children].reverse()) await stopGroup(child);
    this.children = [];
    await this.bridge?.close();
  }

  killNow() {
    for (const child of this.children) {
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch {
        // gone
      }
    }
  }

  // ---- the page bridge ----

  ask(op, query, timeout = 10_000) {
    if (!this.socket) return Promise.reject(new Error("the page bridge is not connected"));
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`the page did not answer ${op}`));
      }, timeout);
      this.pending.set(id, {
        resolve: (v) => (clearTimeout(timer), resolve(v)),
        reject: (e) => (clearTimeout(timer), reject(e)),
      });
      this.socket.send(JSON.stringify({ id, op, query: query === undefined ? undefined : wire(query) }));
    });
  }

  rect(query) {
    return this.ask("rect", query);
  }
  text(query) {
    return this.ask("text", query);
  }
  visible(query) {
    return this.ask("visible", query).catch(() => false);
  }
  count(query) {
    return this.ask("count", query);
  }
  style(query) {
    return this.ask("style", query);
  }
  scrollIntoView(query) {
    return this.ask("scrollIntoView", query);
  }
  state() {
    return this.ask("state");
  }

  /** Until the page has painted two more frames, and a little longer for the X server's copy of them. */
  async settle(ms = 400) {
    await this.ask("frames", undefined, 10_000).catch(() => {});
    await sleep(ms);
  }

  async waitFor(query, timeout = 15_000) {
    await until(`${JSON.stringify(wire(query))} to show`, () => this.visible(query), timeout, 150);
  }

  async waitGone(query, timeout = 15_000) {
    await until(`${JSON.stringify(wire(query))} to go`, async () => !(await this.visible(query)), timeout, 150);
  }

  /** Waits until the page's own state passes `check` (e.g. `(s) => s.zoom === 1.1`). */
  async waitState(check, what = "the page's state", timeout = 10_000) {
    return until(what, async () => {
      const s = await this.state();
      return check(s) ? s : undefined;
    }, timeout, 150);
  }

  // ---- input: the X server's, never the page's ----

  focus(id = this.window) {
    this.xdo("windowfocus", "--sync", id);
  }

  /** The screen point at the middle of what `query` finds (scrolled into view first when it is outside the window). */
  async point(query, { at } = {}) {
    let box = await this.rect(query);
    const outside = box.y < 0 || box.x < 0 || box.y + box.height > box.inner.height || box.x + box.width > box.inner.width;
    if (outside) {
      await this.scrollIntoView(query);
      await sleep(150);
      box = await this.rect(query);
    }
    const win = this.geometry();
    const offsetY = Math.max(0, win.height - Math.round(box.inner.height * box.dpr)); // a title bar, if any
    const fx = at?.x ?? 0.5;
    const fy = at?.y ?? 0.5;
    return { x: Math.round(win.x + (box.x + box.width * fx) * box.dpr), y: Math.round(win.y + offsetY + (box.y + box.height * fy) * box.dpr) };
  }

  async move(query) {
    const p = await this.point(query);
    this.xdo("mousemove", "--sync", p.x, p.y);
    return p;
  }

  /** Until nothing on the page is moving (a view transition swallows clicks; a sliding panel moves its buttons). */
  async waitStill(timeout = 3000) {
    await until("the page to stop moving", async () => (await this.state()).moving === 0, timeout, 100).catch(() => {});
  }

  /** A click on what `query` finds, once it shows and the page stands still. */
  async click(query, { button = 1, double = false, settle = 120, timeout = 15_000 } = {}) {
    this.focus();
    await this.waitFor(query, timeout);
    await this.waitStill();
    const p = await this.point(query);
    this.xdo("mousemove", "--sync", p.x, p.y);
    await sleep(40);
    this.xdo("click", ...(double ? ["--repeat", "2", "--delay", "80"] : []), button);
    await sleep(settle);
    return p;
  }

  /** Types through the keyboard. A character the US keyboard has no key for (Arabic, ٠١٢…) is first put on a spare
   * key of its own for the rest of the run (keymap.py), so xdotool never relabels a key mid-word. */
  async type(text, { delay = 35 } = {}) {
    const missing = [...new Set(text)].filter((c) => c.codePointAt(0) > 0x7e && !this.keys.has(c));
    if (missing.length) {
      execFileSync("python3", [path.join(root, "scripts", "realapp", "keymap.py"), "map", missing.join("")], { env: this.env, stdio: ["ignore", "ignore", "pipe"] });
      for (const c of missing) this.keys.add(c);
      await sleep(300); // the window reads the new keyboard map (MappingNotify) before the first key
    }
    this.focus(this.typingInto ?? this.window);
    this.xdo("type", "--delay", delay, "--", text);
    await sleep(100);
  }

  /** Clicks the field `query`, types `text` on the keyboard, and waits until the field holds it: the window may still
   * be taking keys after xdotool has sent them all. `{ ok, got }`: ok when the field ends with exactly `text`. */
  async typeInto(query, text, { timeout = 30_000 } = {}) {
    await this.click(query);
    if (!(await this.ask("hasFocus", query))) {
      await sleep(500);
      await this.click(query); // the first click landed while the page was busy
      if (!(await this.ask("hasFocus", query))) throw new Error(`a click on ${JSON.stringify(wire(query))} did not put the cursor there`);
    }
    const before = await this.text(query);
    await this.type(text);
    const end = Date.now() + timeout;
    let got = await this.text(query);
    let same = Date.now();
    while (got !== before + text && Date.now() < end && Date.now() - same < 3000) {
      await sleep(200);
      const now = await this.text(query);
      if (now !== got) same = Date.now();
      got = now;
    }
    return { ok: got === before + text, got: got.slice(before.length) };
  }

  /** One key or a chord, as xdotool names them: "Return", "ctrl+equal", "ctrl+shift+f". */
  async key(combo, { settle = 150 } = {}) {
    this.focus(this.typingInto ?? this.window);
    this.xdo("key", "--delay", 40, ...combo.split(" "));
    await sleep(settle);
  }

  /** The mouse wheel over what `query` finds (or where the mouse is): `dy` notches down (negative: up), `dx` sideways. */
  async scroll(query, { dy = 3, dx = 0 } = {}) {
    if (query) await this.move(query);
    if (dy) this.xdo("click", "--repeat", Math.abs(dy), "--delay", 30, dy > 0 ? 5 : 4);
    if (dx) this.xdo("click", "--repeat", Math.abs(dx), "--delay", 30, dx > 0 ? 7 : 6);
    await sleep(150);
  }

  /** Presses on `from`, moves in steps to `to` (a query or `{ x, y }` on the screen), lets go. */
  async drag(from, to, { steps = 12 } = {}) {
    this.focus();
    const a = await this.point(from);
    const b = to.x !== undefined && to.y !== undefined && !to.role ? to : await this.point(to);
    this.xdo("mousemove", "--sync", a.x, a.y);
    this.xdo("mousedown", 1);
    for (let i = 1; i <= steps; i++) {
      this.xdo("mousemove", "--sync", Math.round(a.x + ((b.x - a.x) * i) / steps), Math.round(a.y + ((b.y - a.y) * i) / steps));
      await sleep(16);
    }
    this.xdo("mouseup", 1);
    await sleep(150);
  }

  /** The window's size, as dragging its corner would; waits until the page has it. */
  async resize(width, height) {
    if (width > this.screen.width || height > this.screen.height)
      throw new Error(`${width}×${height} is larger than the screen (${this.screen.width}×${this.screen.height}): launch({ screen })`);
    this.xdo("windowsize", "--sync", this.window, width, height);
    let seen;
    await until(`the page at ${width}×${height}`, async () => {
      const s = await this.state();
      seen = s.inner;
      return Math.round(s.inner.width * s.dpr) === width && Math.abs(Math.round(s.inner.height * s.dpr) - height) <= 40;
    }, 10_000, 150).catch((error) => {
      throw new Error(`${error.message} (the page has ${JSON.stringify(seen)}, the window ${JSON.stringify(this.geometry())})`);
    });
    await this.settle(); // the scale's next frame, and the screen painted at the new size
  }

  /** Picks files in the native file chooser (GTK's) that a click on `opener` opens (no opener: it is open already):
   * the path typed in its location field (Ctrl+L), then Enter. GTK's location field takes one path, and picking
   * several in its list by keyboard did not hold up (Enter there completes the path instead of opening the folder),
   * so several files take one dialog each: `again` (default `opener`) opens it for the second file on. */
  async chooseFiles(opener, paths, { again = opener } = {}) {
    for (const [i, file] of paths.entries()) {
      const by = i === 0 ? opener : again;
      if (i > 0 && !by) throw new Error("chooseFiles: several files need an opener (or `again`) for the second one on");
      if (by) await this.click(by);
      const dialog = await until("the file dialog", () => this.otherWindow(), 15_000, 200);
      this.typingInto = dialog;
      try {
        await sleep(600); // the dialog draws its folder before it takes keys
        await this.key("ctrl+l");
        await this.type(path.resolve(file));
        await sleep(300 + 15 * file.length); // the dialog may still be taking the keys
        await this.key("Return");
        await until("the file dialog to close", () => !this.findWindows().includes(dialog), 15_000, 200);
      } finally {
        this.typingInto = undefined;
      }
      this.focus();
      await sleep(300);
    }
  }

  /** The id of a window that opened on our screen besides the main one (a dialog), if any. */
  otherWindow() {
    return this.findWindows().find((id) => id !== this.window);
  }

  /** Waits for a window besides the main one (a dialog) and returns its id. */
  waitWindow(timeout = 15_000) {
    return until("another window (a dialog)", () => this.otherWindow(), timeout, 200);
  }

  // ---- screenshots and video ----

  /** The ONE window as the X server has it, into the shots folder; `screen: true` takes the whole screen (dialogs). */
  async shot(name, { screen = false } = {}) {
    await this.settle(150);
    this.n += 1;
    const file = path.join(this.shotsDir, `${String(this.n).padStart(2, "0")}-${name}.png`);
    execFileSync("import", ["-window", screen ? "root" : this.window, file], { env: this.env, stdio: "ignore" });
    return file;
  }

  /** A short video of the screen (ffmpeg x11grab), until stopVideo(). */
  startVideo(name = "walk") {
    const file = path.join(this.shotsDir, `${name}.mp4`);
    rmSync(file, { force: true });
    this.recording = spawn(
      "ffmpeg",
      ["-loglevel", "error", "-f", "x11grab", "-framerate", "12", "-video_size", `${this.screen.width}x${this.screen.height}`, "-i", `:${this.display}`, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", file],
      { env: this.env, stdio: ["pipe", "ignore", "inherit"] },
    );
    this.videoFile = file;
    return file;
  }

  async stopVideo() {
    const rec = this.recording;
    this.recording = undefined;
    if (!rec || rec.exitCode !== null) return this.videoFile;
    const done = new Promise((resolve) => rec.once("exit", resolve));
    rec.stdin.write("q");
    await Promise.race([done, sleep(5000).then(() => rec.kill("SIGKILL"))]);
    return this.videoFile;
  }

  /** A copy of `file` in this run's folder (walks never touch the originals). */
  scratchCopy(file) {
    const folder = path.join(this.dir, "files");
    mkdirSync(folder, { recursive: true });
    const copy = path.join(folder, path.basename(file));
    copyFileSync(file, copy);
    return copy;
  }

  logs() {
    return Object.fromEntries(readdirSync(this.dir).filter((f) => f.endsWith(".log")).map((f) => [f, path.join(this.dir, f)]));
  }
}

/** Starts the screen, the bench's core and Vite, and the ONE window; `stop()` ends them all.
 * Options: width, height (1920×1080), firstLaunch (forget the first launch's answers), shots (folder), verbose,
 * display, port, keep (keep the data folder), keepProfile (keep the window's web storage), compositing, dir (the run
 * folder: data, logs), core ("bench", the default: the scripted AI; "real": the real core with real AI providers,
 * realcore.py, in the same throw-away data folder with keyring's fail backend, no Claude Code and no browser). */
export async function launch(opts = {}) {
  const app = new RealApp(opts);
  try {
    return await app.start();
  } catch (error) {
    await app.stop();
    throw error;
  }
}
