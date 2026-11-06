// The start screen (docs/specs/2026-11-05-motion-design.md, section 1): the mark draws itself while the core starts,
// ONE and the slogan come in, and the screen leaves once both the drawing and the core are done.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { texts } from "../i18n";
import { HealthGate } from "./CoreDown";
import { INTRO_MS, SLOW_MS } from "./StartScreen";

const logPath = "/tmp/qs-mind-one/core.log";
const startScreen = () => document.querySelector("[data-start-screen]");

/** The core answers /health after `ms`; never, when `ms` is Infinity; with an error, when `down`. The zoom it reads once
 * the core is up (ui/scale.ts) is answered at once. */
function coreReadyAfter(ms: number, down = false) {
  const fetch = vi.fn(
    (url: RequestInfo | URL) =>
      new Promise<Response>((resolve, reject) => {
        if (String(url) === "/api/settings/zoom") return resolve(Response.json({ zoom: 1 }));
        if (ms === Infinity) return;
        setTimeout(() => (down ? reject(new TypeError("Failed to fetch")) : resolve(Response.json({ ok: true }))), ms);
      }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function reducedMotion(on: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: on, addEventListener() {}, removeEventListener() {} })),
  );
}

function systemLanguageIs(tag: string) {
  vi.spyOn(navigator, "languages", "get").mockReturnValue([tag]);
}

beforeEach(() => systemLanguageIs("en-US"));
afterEach(() => vi.useRealTimers());

describe("the start screen", () => {
  it("a core ready at 50 ms: ONE shows only once the drawing ends, and never a blank frame between", async () => {
    vi.useFakeTimers();
    coreReadyAfter(50);
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    let shownAt: number | undefined;
    for (let at = 0; at <= 2000; at += 50) {
      const app = screen.queryByText("chat");
      expect(app !== null || startScreen() !== null).toBe(true); // RF2: one or the other, every frame
      if (app && shownAt === undefined) shownAt = at;
      await act(() => vi.advanceTimersByTimeAsync(50));
    }
    expect(shownAt).toBeGreaterThanOrEqual(1000);
    expect(shownAt).toBeLessThan(1600);
    expect(INTRO_MS).toBeLessThan(1500);
    expect(startScreen()).toBeNull(); // and it has left
  });

  it("leaves with a clean cut: its words fade on Paper, then ONE takes its place; never the two at once (tender day)", async () => {
    vi.useFakeTimers();
    coreReadyAfter(50);
    let finish = () => {};
    const animate = vi.fn(() => ({ finished: new Promise<void>((resolve) => (finish = resolve)), finish() {}, cancel() {} }));
    HTMLElement.prototype.animate = animate as unknown as typeof HTMLElement.prototype.animate;
    try {
      render(<HealthGate logPath={logPath}>chat</HealthGate>);
      await act(() => vi.advanceTimersByTimeAsync(INTRO_MS + 100));
      const fading = animate.mock.contexts.at(-1) as unknown as HTMLElement;
      expect(fading.hasAttribute("data-start-screen")).toBe(false); // its words fade; its Paper stays whole
      expect(screen.queryByText("chat")).toBeNull(); // ONE is not drawn under a fading screen
      await act(async () => finish());
      expect(screen.getByText("chat")).toBeInTheDocument();
      expect(startScreen()).toBeNull();
    } finally {
      delete (HTMLElement.prototype as { animate?: unknown }).animate;
    }
  });

  it("a core slower than the drawing: ONE shows as soon as it is ready", async () => {
    vi.useFakeTimers();
    coreReadyAfter(2000);
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    await act(() => vi.advanceTimersByTimeAsync(1990));
    expect(screen.queryByText("chat")).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(20));
    expect(screen.getByText("chat")).toBeInTheDocument();
  });

  it("a core still starting after 3 s: one quiet line says so, once", async () => {
    vi.useFakeTimers();
    coreReadyAfter(Infinity);
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    await act(() => vi.advanceTimersByTimeAsync(SLOW_MS - 10));
    expect(screen.queryByText(texts.startEngine.en)).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(20));
    expect(screen.getAllByText(texts.startEngine.en)).toHaveLength(1);
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screen.getAllByText(texts.startEngine.en)).toHaveLength(1);
  });

  it("a core down: the reason, its log and Retry on the same screen; Retry checks again", async () => {
    const fetch = coreReadyAfter(0, true);
    const user = userEvent.setup();
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    expect(await screen.findByText(texts.coreDown.en)).toBeInTheDocument();
    expect(screen.queryByText(texts.coreDown.ar)).toBeNull();
    expect(screen.getByText(logPath)).toBeInTheDocument();
    expect(startScreen()).toContainElement(screen.getByText(logPath));
    expect(startScreen()).toContainElement(screen.getByText(texts.startSlogan.en.split(" ")[0]!));
    expect(fetch).toHaveBeenCalledTimes(1);
    const again = coreReadyAfter(0);
    await user.click(screen.getByRole("button", { name: texts.retry.en }));
    expect(await screen.findByText("chat", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(again.mock.calls.filter(([url]) => url === "/api/health")).toHaveLength(1); // then the zoom
  });

  it("with reduced motion: the mark whole, no drawing, and ONE at once when the core is ready", async () => {
    vi.useFakeTimers();
    reducedMotion(true);
    coreReadyAfter(50);
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    expect(startScreen()!.querySelector("[data-draw]")).toBeNull();
    expect(startScreen()!.querySelector("[data-mark]")).not.toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(60));
    expect(screen.getByText("chat")).toBeInTheDocument();
    expect(startScreen()).toBeNull();
  });

  it("draws the mark's lines, then fills its face, when motion is on", () => {
    coreReadyAfter(Infinity);
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    const mark = startScreen()!.querySelector("[data-mark]")!;
    expect(mark.getAttribute("data-draw")).toBe("");
    const lines = mark.querySelectorAll<SVGPathElement>("path.mark-line");
    expect(lines.length).toBeGreaterThan(50);
    for (const line of lines) expect(Number(line.style.getPropertyValue("--len"))).toBeGreaterThan(0);
    expect(mark.querySelector("polygon.mark-face")).not.toBeNull();
  });

  it("the slogan comes word by word: one span per whole word, never per letter", () => {
    coreReadyAfter(Infinity);
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    const words = [...startScreen()!.querySelectorAll("[data-word]")].map((w) => w.textContent);
    expect(words).toEqual(texts.startSlogan.en.split(" "));
  });
});

describe("the start screen's language", () => {
  afterEach(() => vi.resetModules());

  async function freshGate() {
    vi.resetModules(); // the saved language is read once, when the page loads
    const { HealthGate: Gate } = await import("./CoreDown");
    return Gate;
  }

  it("is the saved language", async () => {
    localStorage.setItem("qsone.language", "ar");
    const Gate = await freshGate();
    coreReadyAfter(Infinity);
    render(<Gate logPath={logPath}>chat</Gate>);
    expect(startScreen()!.getAttribute("lang")).toBe("ar");
    expect(startScreen()!.getAttribute("dir")).toBe("rtl");
    expect([...startScreen()!.querySelectorAll("[data-word]")].map((w) => w.textContent)).toEqual(texts.startSlogan.ar.split(" "));
  });

  it("is the system's on the very first launch", async () => {
    systemLanguageIs("ar-EG");
    const Gate = await freshGate();
    coreReadyAfter(Infinity);
    render(<Gate logPath={logPath}>chat</Gate>);
    expect(startScreen()!.getAttribute("lang")).toBe("ar");
  });

  it("is English on the very first launch of an English system", async () => {
    const Gate = await freshGate();
    coreReadyAfter(Infinity);
    render(<Gate logPath={logPath}>chat</Gate>);
    expect(startScreen()!.getAttribute("lang")).toBe("en");
  });
});
