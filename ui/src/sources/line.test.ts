import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DUR, EASE } from "../ui/motion";
import { hideSourceLine, showSourceLine, sourceLineHandlers } from "./line";
import { sourceKeys } from "./targets";

function at(rect: DOMRect, attrs: Record<string, string> = {}) {
  const el = document.createElement("div");
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  el.getBoundingClientRect = () => rect;
  document.body.append(el);
  return el;
}

function reduced(on: boolean) {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: on, addEventListener() {}, removeEventListener() {} })));
}

const line = () => document.querySelector<SVGPathElement>('svg[data-source-overlay] path[data-source="line"]');
const keys = sourceKeys({ fileId: "f1", locator: { sheet: "BOQ", row: 41 } });

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  hideSourceLine();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("the source line", () => {
  it("draws one Ink line once, in about 300 ms, from the number to its source row", () => {
    reduced(false);
    const animate = vi.fn(() => ({ finished: Promise.resolve(), finish() {} }));
    SVGElement.prototype.animate = animate as unknown as typeof SVGElement.prototype.animate;
    const number = at(new DOMRect(600, 100, 60, 20));
    at(new DOMRect(100, 300, 300, 30), { "data-source-at": "file:f1#sheet=BOQ&row=41" });
    expect(showSourceLine(number, keys)).toBe(true);
    const path = line()!;
    expect(path.getAttribute("d")).toMatch(/^M 600 110 C .* 400 315$/);
    expect(path.getAttribute("pathLength")).toBe("1");
    expect(path.style.stroke).toContain("--color-ink");
    expect(path.style.strokeWidth).toBe("1");
    expect(animate).toHaveBeenCalledTimes(1); // once: no travelling light, no loop
    expect(animate).toHaveBeenCalledWith([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], { duration: DUR.long, easing: EASE });
    delete (SVGElement.prototype as { animate?: unknown }).animate;
  });

  it("draws only when both ends are on screen", () => {
    reduced(true);
    const number = at(new DOMRect(600, 100, 60, 20));
    const offscreen = at(new DOMRect(100, innerHeight + 50, 300, 30), { "data-source-at": "file:f1#sheet=BOQ&row=41" });
    expect(showSourceLine(number, keys)).toBe(false);
    expect(line()).toBeNull();
    offscreen.getBoundingClientRect = () => new DOMRect(100, 300, 300, 30);
    const hidden = at(new DOMRect(600, -80, 60, 20)); // the number itself scrolled away
    expect(showSourceLine(hidden, keys)).toBe(false);
    expect(line()).toBeNull();
    expect(showSourceLine(number, keys)).toBe(true);
  });

  it("goes to the frame when the exact row is not drawn, and draws nothing when the source is not open", () => {
    reduced(true);
    const number = at(new DOMRect(600, 100, 60, 20));
    expect(showSourceLine(number, keys)).toBe(false);
    at(new DOMRect(50, 50, 400, 500), { "data-frame": "file:f1" });
    expect(showSourceLine(number, keys)).toBe(true);
  });

  it("with reduced motion the line shows whole at once, and goes at once", () => {
    reduced(true);
    const number = at(new DOMRect(600, 100, 60, 20));
    at(new DOMRect(100, 300, 300, 30), { "data-source-at": "file:f1" });
    showSourceLine(number, keys);
    expect(line()!.style.strokeDashoffset).toBe("0");
    hideSourceLine(number);
    expect(line()).toBeNull();
  });

  it("follows the number when its chat scrolls, and hides while either end is off screen", async () => {
    reduced(true);
    let top = 100;
    const number = at(new DOMRect(600, 100, 60, 20));
    number.getBoundingClientRect = () => new DOMRect(600, top, 60, 20);
    at(new DOMRect(100, 300, 300, 30), { "data-source-at": "file:f1" });
    showSourceLine(number, keys);
    top = 140;
    dispatchEvent(new Event("scroll"));
    await vi.advanceTimersByTimeAsync(20);
    expect(line()!.getAttribute("d")).toMatch(/^M 600 150 /);
    top = -100;
    dispatchEvent(new Event("scroll"));
    await vi.advanceTimersByTimeAsync(20);
    expect(line()!.style.visibility).toBe("hidden");
  });

  it("a number with no source draws nothing and gets no handlers", () => {
    reduced(true);
    expect(sourceKeys(null)).toEqual([]);
    expect(sourceKeys({ numberId: "n1" })).toEqual([]); // the number itself is not its source
    expect(sourceLineHandlers([])).toEqual({});
    at(new DOMRect(100, 300, 300, 30), { "data-source-at": "file:f1" });
    expect(showSourceLine(at(new DOMRect(600, 100, 60, 20)), [])).toBe(false);
    expect(line()).toBeNull();
  });

  it("never draws to the number itself", () => {
    reduced(true);
    const number = at(new DOMRect(600, 100, 60, 20), { "data-source-at": "number:n1" });
    expect(showSourceLine(number, sourceKeys({ numberId: "n1" }, { number: true }))).toBe(false);
    at(new DOMRect(100, 300, 300, 30), { "data-source-at": "number:n1" }); // the same number in a sheet frame
    expect(showSourceLine(number, sourceKeys({ numberId: "n1" }, { number: true }))).toBe(true);
  });
});

describe("source keys", () => {
  it("name the exact place first, then the file, the source and the number", () => {
    expect(sourceKeys({ fileId: "f1", locator: { sheet: "Price List", row: 4, dated_how: "document" }, sourceId: "s1", numberId: "n1" }, { number: true })).toEqual([
      "file:f1#sheet=Price%20List&row=4",
      "file:f1",
      "source:s1",
      "number:n1",
    ]);
    expect(sourceKeys({ fileId: "f1", locator: { page: 3 } })).toEqual(["file:f1#page=3", "file:f1"]);
  });
});
