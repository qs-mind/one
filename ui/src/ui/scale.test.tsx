import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  applyScale,
  currentScale,
  currentZoom,
  fluidScale,
  loadZoom,
  scaled,
  setZoom,
  stepZoom,
  TEXT_FLOOR,
  textScale,
  useZoomKeys,
} from "./scale";

const root = () => document.documentElement.style.fontSize;

describe("the window's scale", () => {
  it("is 100 % at 1920×1080 and on any larger window: nothing grows past today's sizes", () => {
    expect(fluidScale(1920, 1080)).toBe(1);
    expect(fluidScale(2560, 1440)).toBe(1);
    expect(fluidScale(3840, 2160)).toBe(1);
  });

  it("is 80 % at 1280×720, and no smaller below it", () => {
    expect(fluidScale(1280, 720)).toBeCloseTo(0.8, 10);
    expect(fluidScale(1024, 600)).toBeCloseTo(0.8, 10);
  });

  it("goes down in a line between the two, by the smaller of width's and height's", () => {
    expect(fluidScale(1600, 1080)).toBeCloseTo(0.9, 10); // halfway across
    expect(fluidScale(1920, 900)).toBeCloseTo(0.9, 10); // halfway down
    expect(fluidScale(1366, 768)).toBeCloseTo(Math.min(0.8 + 0.2 * (86 / 640), 0.8 + 0.2 * (48 / 360)), 10);
    expect(fluidScale(1536, 864)).toBeCloseTo(0.88, 10);
  });

  it("shrinks a tall narrow window by its width, and a wide short one by its height", () => {
    expect(fluidScale(1280, 1400)).toBeCloseTo(0.8, 10);
    expect(fluidScale(1600, 1400)).toBeCloseTo(0.9, 10);
    expect(fluidScale(2560, 720)).toBeCloseTo(0.8, 10);
    expect(fluidScale(2560, 900)).toBeCloseTo(0.9, 10);
  });
});

describe("text's floor", () => {
  it("keeps body text at 12.5 px in English and 13.5 px in Arabic, however small the screen", () => {
    expect(14 * textScale(0.8, "en")).toBeCloseTo(12.5, 10);
    expect(15 * textScale(0.8, "ar")).toBeCloseTo(13.5, 10);
    expect(14 * textScale(0.64, "en")).toBeCloseTo(12.5, 10); // zoomed out on a small screen too
    expect(TEXT_FLOOR.ar).toBeCloseTo(0.9, 10);
  });

  it("is the screen's scale above the floor", () => {
    expect(textScale(1, "en")).toBe(1);
    expect(textScale(0.95, "ar")).toBe(0.95);
    expect(textScale(1.2, "en")).toBe(1.2);
  });
});

describe("the root font-size", () => {
  it("is 16 px at 100 % and follows the window", () => {
    windowOf(1920, 1080);
    expect(root()).toBe("16px");
    windowOf(1280, 720);
    expect(root()).toBe("12.8px");
    expect(currentScale()).toBe(0.8);
    expect(scaled(320)).toBe(256);
  });

  it("multiplies the window's scale by the zoom", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")));
    windowOf(1920, 1080);
    setZoom(1.5);
    expect(root()).toBe("24px");
    windowOf(1280, 720);
    expect(root()).toBe("19.2px");
  });
});

describe("the engineer's zoom", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("goes in 10 % steps from 80 % to 150 %", () => {
    expect(stepZoom(1, 1)).toBe(1.1);
    expect(stepZoom(1, -1)).toBe(0.9);
    expect(stepZoom(0.8, -1)).toBe(0.8);
    expect(stepZoom(1.5, 1)).toBe(1.5);
    expect(stepZoom(1.1000000000000001, 1)).toBe(1.2);
  });

  function Keys() {
    useZoomKeys();
    return <input aria-label="field" />;
  }
  const press = (target: EventTarget, code: string, init: KeyboardEventInit = {}) =>
    target.dispatchEvent(new KeyboardEvent("keydown", { code, ctrlKey: true, bubbles: true, cancelable: true, ...init }));

  it("steps with Ctrl and = (or +), - and 0, by the key's place (so the Arabic layout works), and is kept in the core", () => {
    const fetch = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    windowOf(1920, 1080);
    render(<Keys />);
    press(document.body, "Equal");
    expect(currentZoom()).toBe(1.1);
    press(document.body, "Equal", { shiftKey: true }); // Ctrl and +
    press(document.body, "NumpadAdd");
    expect(currentZoom()).toBe(1.3);
    expect(root()).toBe("20.8px");
    press(document.body, "Minus");
    expect(currentZoom()).toBe(1.2);
    press(document.body, "Digit0");
    expect(currentZoom()).toBe(1);
    expect(root()).toBe("16px");
    const saves = fetch.mock.calls.map(([url, init]) => [url, JSON.parse(String((init as RequestInit).body))]);
    expect(saves).toEqual([
      ["/api/settings/zoom", { zoom: 1.1 }],
      ["/api/settings/zoom", { zoom: 1.2 }],
      ["/api/settings/zoom", { zoom: 1.3 }],
      ["/api/settings/zoom", { zoom: 1.2 }],
      ["/api/settings/zoom", { zoom: 1 }],
    ]);
    expect(fetch.mock.calls.every(([, init]) => (init as RequestInit).method === "PUT")).toBe(true);
  });

  it("never fires while the engineer types in a field, and needs Ctrl", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")));
    const { getByLabelText } = render(<Keys />);
    press(getByLabelText("field"), "Equal");
    press(document.body, "Equal", { ctrlKey: false });
    press(document.body, "Equal", { altKey: true });
    expect(currentZoom()).toBe(1);
  });

  it("stops the webview's own zoom", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")));
    render(<Keys />);
    const event = new KeyboardEvent("keydown", { code: "Minus", ctrlKey: true, bubbles: true, cancelable: true });
    document.body.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("comes back from the core at start; a missing or odd answer keeps 100 %", async () => {
    windowOf(1920, 1080);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ zoom: 1.2 }))));
    await loadZoom();
    expect(currentZoom()).toBe(1.2);
    expect(root()).toBe("19.2px");

    setZoomQuietly(1);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    await loadZoom();
    expect(currentZoom()).toBe(1);
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("down"))));
    await loadZoom();
    expect(currentZoom()).toBe(1);
  });

  it("is never kept in web storage", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")));
    setZoom(1.4);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

/** Back to 100 % with the save stubbed out. */
function setZoomQuietly(zoom: number) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")));
  setZoom(zoom);
}

/** The window at this size, and the scale for it. */
function windowOf(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
  applyScale();
}
