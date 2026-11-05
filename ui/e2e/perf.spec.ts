// The canvas under load, by hand only: `npm run perf:canvas`, alone on the machine (Chromium, the `perf` project).
// For 300 and 1,000 frames, with the CPU slowed 4× through CDP: the first paint after the layout answer (on the
// first open, when every frame is placed, and on a reopen from the saved layout), 3 s of wheel panning (400 px every
// 16 ms), 3 s of Ctrl+wheel zoom, then zoomed in where frames run their live viewers, panning again. Frames are
// counted by requestAnimationFrame; the JS heap comes from CDP Performance.getMetrics; the live viewers mounted are
// counted all the time. Prints a table and keeps it as perf-canvas.json in test-results/.
// Targets (Plan 7 Task 7): 300 frames: first paint under 800 ms, pan median 45 fps or more, heap under 150 MB;
// 1,000 frames: pan 25 fps or more, heap under 300 MB; never more than six live viewers. A miss fails softly, so the
// whole table is printed; it is fixed or written down with its cause (Task 8).
import { writeFileSync } from "node:fs";
import { expect, test, type CDPSession, type Page } from "@playwright/test";
import { many, mockCore } from "./fixtures";

test.use({ viewport: { width: 1440, height: 900 } });
test.describe.configure({ mode: "serial" });

const CPU_SLOWDOWN = Number(process.env.PERF_CPU ?? 4); // PERF_CPU=1 for a quick look without the slowdown
const PHASE_MS = 3000;
const STEP_MS = 16;

// In the page: when the layout answer arrived, the first frame painted after it, every animation frame while a
// phase records, and the most live viewers ever mounted (a live frame's body holds the viewer's Paper root; a poster
// has none). Installed before the screen's own scripts.
function probe() {
  const w = window as unknown as Record<string, unknown> & { __perf: Perf };
  type Perf = { layoutAt: number | null; firstPaint: number | null; frames: number[]; moves: number; recording: boolean; maxLive: number };
  const perf: Perf = { layoutAt: null, firstPaint: null, frames: [], moves: 0, recording: false, maxLive: 0 };
  let last = "";
  w.__perf = perf;
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await original(input, init);
    const url = String(input instanceof Request ? input.url : input);
    if (/\/canvas$/.test(url) && (init?.method ?? "GET") === "GET") perf.layoutAt = performance.now();
    return response;
  };
  const live = () =>
    document.querySelectorAll('.react-flow__node[data-id^="deliverable:"] [data-frame-body] > .bg-paper').length;
  let drawnAt: number | null = null; // the frame that first had nodes; the next frame starts after it painted
  const tick = (now: number) => {
    if (drawnAt !== null && perf.firstPaint === null) perf.firstPaint = performance.now();
    if (perf.layoutAt !== null && drawnAt === null && document.querySelector(".react-flow__node")) drawnAt = now;
    if (perf.recording) {
      perf.frames.push(now);
      // how many frames showed the view moved: the pan or zoom really happened
      const view = document.querySelector<HTMLElement>(".react-flow__viewport")?.style.transform ?? "";
      if (view !== last) perf.moves += 1;
      last = view;
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  setInterval(() => (perf.maxLive = Math.max(perf.maxLive, live())), 50);
}

type Phase = { fps: number; average: number; p95ms: number; frames: number; moved: number };

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)]! : NaN;
};
const percentile = (xs: number[], p: number) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.min(s.length - 1, Math.floor(s.length * p))]! : NaN;
};

async function record(page: Page, run: () => Promise<void>): Promise<Phase> {
  await page.evaluate(() => {
    const perf = (window as unknown as { __perf: { frames: number[]; moves: number; recording: boolean } }).__perf;
    perf.frames = [];
    perf.moves = 0;
    perf.recording = true;
  });
  await run();
  const { frames, moves } = await page.evaluate(() => {
    const perf = (window as unknown as { __perf: { frames: number[]; moves: number; recording: boolean } }).__perf;
    perf.recording = false;
    return { frames: perf.frames, moves: perf.moves };
  });
  const gaps = frames.slice(1).map((t, i) => t - frames[i]!);
  const span = frames.length > 1 ? frames.at(-1)! - frames[0]! : NaN;
  return { fps: Math.round(1000 / median(gaps)), average: Math.round(((frames.length - 1) * 1000) / span), p95ms: Math.round(percentile(gaps, 0.95)), frames: frames.length, moved: moves };
}

/** Wheel events every 16 ms for 3 s at a point over the canvas, sent in the page (Playwright's own mouse.wheel waits
 * for each event to be handled, so it cannot keep up 60 a second); the direction turns every `turn` events so the
 * frames stay in view. With `zoom`, they carry the zoom modifier (Ctrl, or Cmd on a Mac). */
async function wheel(page: Page, delta: number, turn: number, zoom = false) {
  await page.evaluate(
    ({ delta, turn, zoom, ms, step }) =>
      new Promise<void>((resolve) => {
        const [x, y] = [900, 400]; // clear of the chat (at the left in Arabic) and the bars at the bottom
        const mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
        const end = performance.now() + ms;
        let i = 0;
        const timer = setInterval(() => {
          if (performance.now() >= end) {
            clearInterval(timer);
            return resolve();
          }
          const sign = Math.floor(i++ / turn) % 2 === 0 ? 1 : -1;
          const target = document.elementFromPoint(x, y) ?? document.body;
          const init = { deltaY: sign * delta, clientX: x, clientY: y, bubbles: true, cancelable: true };
          target.dispatchEvent(new WheelEvent("wheel", { ...init, ctrlKey: zoom && !mac, metaKey: zoom && mac }));
        }, step);
      }),
    { delta, turn, zoom, ms: PHASE_MS, step: STEP_MS },
  );
}

async function heapMB(cdp: CDPSession): Promise<number> {
  const { metrics } = await cdp.send("Performance.getMetrics");
  const used = metrics.find((m) => m.name === "JSHeapUsedSize")?.value ?? NaN;
  return Math.round(used / 1024 / 1024);
}

const zoomPercent = async (page: Page) =>
  Number((await page.getByRole("toolbar", { name: "أدوات التكبير" }).locator("bdi").innerText()).replace("%", ""));

const results: Record<string, unknown>[] = [];

for (const n of [300, 1000]) {
  test(`@perf ${n} frames`, async ({ page }, info) => {
    test.setTimeout(240_000);
    await page.addInitScript(probe);
    const core = await mockCore(page, many(n, { saved: false }));
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: CPU_SLOWDOWN });
    const paint = () =>
      page.evaluate(() => {
        const perf = (window as unknown as { __perf: { layoutAt: number; firstPaint: number } }).__perf;
        return Math.round(perf.firstPaint - perf.layoutAt);
      });

    // first open: every frame is placed, then saved; a reopen reads them back from the saved layout
    // (with this many, the fit-all view of a first open is wider than the 10% zoom floor shows, so wait for any frame)
    const drawn = () => page.locator(".react-flow__node").first().waitFor();
    const rendered = () => page.locator(".react-flow__node").count();
    await page.goto("/");
    await drawn();
    await expect.poll(() => page.evaluate(() => (window as unknown as { __perf: { firstPaint: number | null } }).__perf.firstPaint)).not.toBeNull();
    const firstOpen = await paint();
    await expect.poll(() => core.frameSaves.reduce((sum, s) => sum + s.frames.length, 0), { timeout: 30_000 }).toBeGreaterThanOrEqual(n);
    const renderedFirst = await rendered();
    await page.reload();
    await drawn();
    await expect.poll(() => page.evaluate(() => (window as unknown as { __perf: { firstPaint: number | null } }).__perf.firstPaint)).not.toBeNull();
    const reopen = await paint();
    const heapLoaded = await heapMB(cdp);
    const renderedReopen = await rendered();

    // the mouse over the canvas, clear of the chat (at the left in Arabic) and the bars at the bottom
    const pan = await record(page, () => wheel(page, 400, 8));
    const mod = await page.evaluate(() => (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "Meta" : "Control"));
    const zoom = await record(page, () => wheel(page, 100, 10, true));

    // zoomed in, where Deliverable frames run their live viewers, then panning among them
    // (the palette focuses one frame, as the engineer would reach it: zoom up to 100% around it)
    await page.keyboard.press(`${mod}+KeyK`);
    await page.keyboard.type(`بند ${Math.floor(n / 2)} - عينة`);
    await page.getByRole("option", { name: `بند ${Math.floor(n / 2)} - عينة` }).waitFor();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(500); // the camera moves
    await page.getByRole("button", { name: "كبّر" }).click(); // one step up, past the 60% where viewers go live
    await page.waitForTimeout(2000); // the viewers load their views
    const panLive = await record(page, () => wheel(page, 400, 8));
    const heapPeak = await heapMB(cdp);
    const maxLive = await page.evaluate(() => (window as unknown as { __perf: { maxLive: number } }).__perf.maxLive);
    const zoomLive = await zoomPercent(page);

    const row = {
      frames: n,
      "first paint, first open (ms)": firstOpen,
      "frames drawn, first open": renderedFirst,
      "first paint, reopen (ms)": reopen,
      "frames drawn, reopen": renderedReopen,
      "pan fps (median)": pan.fps,
      "pan fps (average)": pan.average,
      "pan slowest 5% (ms)": pan.p95ms,
      "pan: frames drawn / moved": `${pan.frames} / ${pan.moved}`,
      "zoom fps (median)": zoom.fps,
      "zoom fps (average)": zoom.average,
      "zoom slowest 5% (ms)": zoom.p95ms,
      "zoom: frames drawn / moved": `${zoom.frames} / ${zoom.moved}`,
      "zoomed in to (%)": zoomLive,
      "pan zoomed in, fps (median)": panLive.fps,
      "pan zoomed in, fps (average)": panLive.average,
      "pan zoomed in, slowest 5% (ms)": panLive.p95ms,
      "heap after load (MB)": heapLoaded,
      "heap at the end (MB)": heapPeak,
      "live viewers (most at once)": maxLive,
    };
    results.push(row);
    console.log(`\nCanvas performance, ${n} frames, CPU ${CPU_SLOWDOWN}× slower (Chromium ${page.context().browser()?.version()})`);
    console.table(row);
    writeFileSync(info.outputPath("perf-canvas.json"), JSON.stringify(row, null, 2));
    await info.attach("perf-canvas.json", { body: JSON.stringify(row, null, 2), contentType: "application/json" });

    expect(maxLive, "never more than six live viewers").toBeLessThanOrEqual(6);
    expect(maxLive, "zoomed in, some frames run their live viewer").toBeGreaterThan(0);
    if (n === 300) {
      expect.soft(reopen, "300 frames: first paint under 800 ms").toBeLessThan(800);
      expect.soft(pan.fps, "300 frames: pan median 45 fps or more").toBeGreaterThanOrEqual(45);
      expect.soft(Math.max(heapLoaded, heapPeak), "300 frames: heap under 150 MB").toBeLessThan(150);
    } else {
      expect.soft(pan.fps, "1,000 frames: pan 25 fps or more").toBeGreaterThanOrEqual(25);
      expect.soft(Math.max(heapLoaded, heapPeak), "1,000 frames: heap under 300 MB").toBeLessThan(300);
    }
  });
}

test.afterAll(() => {
  if (results.length > 1) console.table(Object.fromEntries(Object.keys(results[0]!).map((k) => [k, results.map((r) => r[k])])));
});
