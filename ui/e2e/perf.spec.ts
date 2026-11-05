// The workspace under load, by hand only: `npm run perf:workspace`, alone on the machine (Chromium, the `perf`
// project). For a project of 300 and 1,000 Deliverables whose open sheet has as many rows, with the CPU slowed 4×
// through CDP: the first paint of the document after the workspace answer (and again on a reopen), opening the
// document switcher with every Deliverable listed, picking one until its rows show, then 3 s of wheel scrolling in
// the sheet (400 px every 16 ms). Frames are counted by requestAnimationFrame; the JS heap comes from CDP
// Performance.getMetrics. Prints a table and keeps it as perf-workspace.json in test-results/.
// Targets: first paint under 800 ms; the switcher open, and a document picked, under 500 ms; scroll median 45 fps or
// more at 300 and 25 or more at 1,000; heap under 150 MB at 300 and 300 MB at 1,000. A miss fails softly, so the
// whole table is printed; it is fixed or written down with its cause.
// A known miss (5 Nov 2026): at 1,000 Deliverables the switcher opens in 582–589 ms and a picked document shows its
// rows in 681–687 ms, because the switcher renders every Deliverable (no virtual list). That case is marked to fail
// until the virtual list comes; when it passes, the mark goes.
import { writeFileSync } from "node:fs";
import { expect, test, type CDPSession, type Page } from "@playwright/test";
import { many, mockCore, switcher } from "./fixtures";

test.use({ viewport: { width: 1440, height: 900 } });
test.describe.configure({ mode: "serial" });

const CPU_SLOWDOWN = Number(process.env.PERF_CPU ?? 4); // PERF_CPU=1 for a quick look without the slowdown
const PHASE_MS = 3000;
const STEP_MS = 16;

// In the page: when the workspace answer arrived, the first frame painted after the sheet showed rows, and every
// animation frame while a phase records. Installed before the screen's own scripts.
function probe() {
  const w = window as unknown as Record<string, unknown> & { __perf: Perf };
  type Perf = { answerAt: number | null; firstPaint: number | null; frames: number[]; recording: boolean };
  const perf: Perf = { answerAt: null, firstPaint: null, frames: [], recording: false };
  w.__perf = perf;
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await original(input, init);
    const url = String(input instanceof Request ? input.url : input);
    if (/\/workspace$/.test(url) && (init?.method ?? "GET") === "GET") perf.answerAt = performance.now();
    return response;
  };
  let drawnAt: number | null = null; // the frame that first had rows; the next frame starts after it painted
  const tick = (now: number) => {
    if (drawnAt !== null && perf.firstPaint === null) perf.firstPaint = performance.now();
    if (perf.answerAt !== null && drawnAt === null && document.querySelector('[data-region="document"] [role="row"]')) drawnAt = now;
    if (perf.recording) perf.frames.push(now);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

type Phase = { fps: number; average: number; p95ms: number; frames: number };

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
    const perf = (window as unknown as { __perf: { frames: number[]; recording: boolean } }).__perf;
    perf.frames = [];
    perf.recording = true;
  });
  await run();
  const frames = await page.evaluate(() => {
    const perf = (window as unknown as { __perf: { frames: number[]; recording: boolean } }).__perf;
    perf.recording = false;
    return perf.frames;
  });
  const gaps = frames.slice(1).map((t, i) => t - frames[i]!);
  const span = frames.length > 1 ? frames.at(-1)! - frames[0]! : NaN;
  return { fps: Math.round(1000 / median(gaps)), average: Math.round(((frames.length - 1) * 1000) / span), p95ms: Math.round(percentile(gaps, 0.95)), frames: frames.length };
}

/** Wheel events every 16 ms for 3 s over the sheet, sent in the page (Playwright's own mouse.wheel waits for each
 * event to be handled, so it cannot keep up 60 a second); the direction turns every `turn` events. */
async function wheel(page: Page, delta: number, turn: number) {
  const sheet = (await page.locator("[data-document-sheet]").boundingBox())!;
  await page.evaluate(
    ({ delta, turn, ms, step, x, y }) =>
      new Promise<void>((resolve) => {
        const end = performance.now() + ms;
        let i = 0;
        const timer = setInterval(() => {
          if (performance.now() >= end) {
            clearInterval(timer);
            return resolve();
          }
          const sign = Math.floor(i++ / turn) % 2 === 0 ? 1 : -1;
          const target = document.elementFromPoint(x, y) ?? document.body;
          target.dispatchEvent(new WheelEvent("wheel", { deltaY: sign * delta, clientX: x, clientY: y, bubbles: true, cancelable: true }));
          // a wheel event does not scroll by itself when dispatched: the scrolling box under the pointer is moved
          let box: Element | null = target;
          while (box && !(box instanceof HTMLElement && box.scrollHeight > box.clientHeight + 1 && getComputedStyle(box).overflowY !== "visible")) box = box.parentElement;
          box?.scrollBy({ top: sign * delta });
        }, step);
      }),
    { delta, turn, ms: PHASE_MS, step: STEP_MS, x: sheet.x + sheet.width / 2, y: sheet.y + sheet.height / 2 },
  );
}

async function heapMB(cdp: CDPSession): Promise<number> {
  const { metrics } = await cdp.send("Performance.getMetrics");
  const used = metrics.find((m) => m.name === "JSHeapUsedSize")?.value ?? NaN;
  return Math.round(used / 1024 / 1024);
}

const results: Record<string, unknown>[] = [];

for (const n of [300, 1000]) {
  test(`@perf ${n} Deliverables, ${n} rows`, async ({ page }, info) => {
    test.setTimeout(240_000);
    test.fail(n === 1000, "known miss: the switcher renders every Deliverable, no virtual list (582–589 / 681–687 ms)");
    await page.addInitScript(probe);
    const scene = many(n);
    scene.sheetRows = n;
    await mockCore(page, scene);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: CPU_SLOWDOWN });
    const firstPaint = async () => {
      await expect.poll(() => page.evaluate(() => (window as unknown as { __perf: { firstPaint: number | null } }).__perf.firstPaint), { timeout: 60_000 }).not.toBeNull();
      return page.evaluate(() => {
        const perf = (window as unknown as { __perf: { answerAt: number; firstPaint: number } }).__perf;
        return Math.round(perf.firstPaint - perf.answerAt);
      });
    };

    await page.goto("/");
    const firstOpen = await firstPaint();
    await page.reload();
    const reopen = await firstPaint();
    const heapLoaded = await heapMB(cdp);

    // the switcher, every Deliverable listed
    let started = Date.now();
    await switcher(page).click();
    await expect(page.getByRole("menu").getByRole("menuitem")).toHaveCount(n + 1); // and Project files
    const switcherOpen = Date.now() - started;
    const pickName = scene.deliverables.find((d, i) => i >= n / 3 && d.kind === "sheet")!.title; // a sheet: its rows show
    started = Date.now();
    await page.getByRole("menu").getByRole("menuitem", { name: new RegExp(`^${pickName}`) }).click();
    await expect(page.locator('[data-region="document"]')).toHaveAttribute("aria-label", pickName);
    await page.locator('[data-region="document"] [role="row"]').nth(2).waitFor();
    const picked = Date.now() - started;

    const scroll = await record(page, () => wheel(page, 400, 8));
    const heapPeak = await heapMB(cdp);

    const row = {
      deliverables: n,
      "sheet rows": n,
      "first paint, first open (ms)": firstOpen,
      "first paint, reopen (ms)": reopen,
      "switcher open, all listed (ms)": switcherOpen,
      "document picked, rows shown (ms)": picked,
      "scroll fps (median)": scroll.fps,
      "scroll fps (average)": scroll.average,
      "scroll slowest 5% (ms)": scroll.p95ms,
      "heap after load (MB)": heapLoaded,
      "heap at the end (MB)": heapPeak,
    };
    results.push(row);
    console.log(`\nWorkspace performance, ${n} Deliverables, CPU ${CPU_SLOWDOWN}× slower (Chromium ${page.context().browser()?.version()})`);
    console.table(row);
    writeFileSync(info.outputPath("perf-workspace.json"), JSON.stringify(row, null, 2));
    await info.attach("perf-workspace.json", { body: JSON.stringify(row, null, 2), contentType: "application/json" });

    expect.soft(reopen, "first paint under 800 ms").toBeLessThan(800);
    expect.soft(switcherOpen, "the switcher opens with every document under 500 ms").toBeLessThan(500);
    expect.soft(picked, "a picked document shows its rows under 500 ms").toBeLessThan(500);
    expect.soft(scroll.fps, `${n}: scroll median ${n === 300 ? 45 : 25} fps or more`).toBeGreaterThanOrEqual(n === 300 ? 45 : 25);
    expect.soft(Math.max(heapLoaded, heapPeak), `${n}: heap under ${n === 300 ? 150 : 300} MB`).toBeLessThan(n === 300 ? 150 : 300);
  });
}

test.afterAll(() => {
  if (results.length > 1) console.table(Object.fromEntries(Object.keys(results[0]!).map((k) => [k, results.map((r) => r[k])])));
});
