import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DUR, EASE } from "../ui/motion";
import { MARK_HOLD_MS, markSource, readingDirection, revealSource } from "./mark";

function at(rect: DOMRect, parent: Element = document.body, tag = "div") {
  const el = document.createElement(tag);
  el.getBoundingClientRect = () => rect;
  parent.append(el);
  return el;
}

function reduced(on: boolean) {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: on, addEventListener() {}, removeEventListener() {} })));
}

const shape = (kind: string) => document.querySelector<SVGElement>(`svg[data-source-overlay] [data-source="${kind}"]`);
const cell = new DOMRect(100, 50, 80, 20);

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete (SVGElement.prototype as { animate?: unknown }).animate;
  document.body.innerHTML = "";
  document.documentElement.dir = "";
});

describe("the source mark", () => {
  it("draws a solid Copper box round the figure from the left in English, then fades after the hold", async () => {
    reduced(false);
    const animate = vi.fn(() => ({ finished: Promise.resolve(), finish() {} }));
    SVGElement.prototype.animate = animate as unknown as typeof SVGElement.prototype.animate;
    const page = at(new DOMRect(0, 0, 800, 600));
    page.setAttribute("dir", "ltr");
    const done = markSource(at(cell, page));
    const pen = shape("mark")!;
    expect(pen.getAttribute("d")).toBe("M 97 47 H 183 V 73 H 97 Z");
    expect(pen.style.stroke).toContain("--color-copper");
    expect(pen.style.strokeDasharray).toBe("none");
    await vi.advanceTimersByTimeAsync(MARK_HOLD_MS - 1);
    expect(shape("mark")).not.toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    await done;
    expect(animate).toHaveBeenLastCalledWith([{ opacity: 1 }, { opacity: 0 }], { duration: DUR.long, easing: EASE });
    expect(shape("mark")).toBeNull();
  });

  it("flips in Arabic: the pen starts at the right", async () => {
    reduced(true);
    const page = at(new DOMRect(0, 0, 800, 600));
    page.setAttribute("dir", "rtl");
    const number = at(cell, page, "bdi");
    number.setAttribute("dir", "ltr"); // a number isolated left to right is still read in the Arabic row
    void markSource(number);
    expect(shape("mark")!.getAttribute("d")).toBe("M 183 47 H 97 V 73 H 183 Z");
    expect(readingDirection(number)).toBe("rtl");
  });

  it("with reduced motion the mark and the flash show whole at once, and go at once after the hold", async () => {
    reduced(true);
    const animate = vi.fn();
    SVGElement.prototype.animate = animate as unknown as typeof SVGElement.prototype.animate;
    const row = at(new DOMRect(0, 45, 800, 30));
    const done = markSource(at(cell, row), { row });
    expect(shape("mark")!.style.strokeDashoffset).toBe("0");
    expect(shape("flash")!.style.fill).toContain("--color-stone");
    expect(shape("flash")!.getAttribute("width")).toBe("800");
    await vi.advanceTimersByTimeAsync(MARK_HOLD_MS);
    await done;
    expect(shape("mark")).toBeNull();
    expect(shape("flash")).toBeNull();
    expect(animate).not.toHaveBeenCalled();
  });

  it("marks nothing off screen", async () => {
    reduced(true);
    await markSource(at(new DOMRect(100, innerHeight + 20, 80, 20)));
    expect(shape("mark")).toBeNull();
  });

  it("a newer mark takes over at once", () => {
    reduced(true);
    void markSource(at(cell));
    void markSource(at(new DOMRect(300, 50, 80, 20)));
    expect(document.querySelectorAll('[data-source="mark"]')).toHaveLength(1);
  });
});

describe("revealing an opened source", () => {
  it("waits for the source row to show, then marks it and flashes its row", async () => {
    reduced(true);
    const found = revealSource(["file:f1#sheet=BOQ&row=41", "file:f1"]);
    await vi.advanceTimersByTimeAsync(100); // the file's text is loading
    const li = at(new DOMRect(0, 200, 400, 40), document.body, "li");
    li.setAttribute("data-source-at", "file:f1#sheet=BOQ&row=41");
    await vi.advanceTimersByTimeAsync(200);
    expect(await found).toBe(true);
    expect(shape("mark")).not.toBeNull();
    expect(shape("flash")!.getAttribute("y")).toBe("200");
  });

  it("marks no whole frame and no PDF page (no place on a page is known yet)", async () => {
    reduced(true);
    at(new DOMRect(0, 0, 400, 400)).setAttribute("data-frame", "file:f1");
    const found = revealSource(["file:f1#page=3", "file:f1"]);
    await vi.advanceTimersByTimeAsync(2100);
    expect(await found).toBe(false); // the page never showed
    expect(shape("mark")).toBeNull();
  });

  it("a page-level source counts as found once its page shows, with nothing marked on it", async () => {
    reduced(true);
    const found = revealSource(["file:f1#page=3", "file:f1"], ["3,450"]);
    await vi.advanceTimersByTimeAsync(100); // the page image is loading
    at(new DOMRect(0, 0, 600, 800), document.body, "img").setAttribute("data-source-at", "file:f1#page=3");
    await vi.advanceTimersByTimeAsync(50);
    expect(await found).toBe(true);
    expect(shape("mark")).toBeNull();
  });

  it("another page of the file is not the source's page", async () => {
    reduced(true);
    at(new DOMRect(0, 0, 600, 800), document.body, "img").setAttribute("data-source-at", "file:f1#page=1");
    const found = revealSource(["file:f1#page=3", "file:f1"]);
    await vi.advanceTimersByTimeAsync(2100);
    expect(await found).toBe(false);
  });

  it("gives up when the source never shows", async () => {
    reduced(true);
    const found = revealSource(["number:n9"]);
    await vi.advanceTimersByTimeAsync(2100);
    expect(await found).toBe(false);
  });
});


describe("real-walk sheet source (sample data)", () => {
  it("finds 80,640 in the row's 80640 cell, centers it, and paints a solid mark for two seconds", async () => {
    reduced(true);
    const row = at(new DOMRect(0, 45, 800, 30));
    row.setAttribute("role", "row");
    const first = at(new DOMRect(10, 50, 50, 20), row);
    first.textContent = "20";
    first.setAttribute("data-source-at", "file:sample#sheet=BOQ&row=20");
    const amount = at(cell, row);
    amount.textContent = "80640";
    amount.scrollIntoView = vi.fn();
    const found = revealSource(["file:sample#sheet=BOQ&row=20"], ["80,640"]);
    await vi.advanceTimersByTimeAsync(100);
    expect(await found).toBe(true);
    expect(amount.scrollIntoView).toHaveBeenCalledWith({ block: "center", inline: "center" });
    expect(shape("mark")!.getAttribute("d")).toBe("M 97 47 H 183 V 73 H 97 Z");
    expect(shape("mark")!.style.strokeDasharray).toBe("none");
    await vi.advanceTimersByTimeAsync(2000);
    expect(shape("mark")).not.toBeNull();
  });

  it("does not match the figure 15 inside the different number 115", async () => {
    reduced(true);
    const row = at(new DOMRect(0, 45, 800, 30));
    row.setAttribute("role", "row");
    const first = at(new DOMRect(10, 50, 50, 20), row);
    first.textContent = "115";
    first.setAttribute("data-source-at", "file:sample#row=17");
    const amount = at(cell, row);
    amount.textContent = "15.00";
    amount.scrollIntoView = vi.fn();
    const found = revealSource(["file:sample#row=17"], ["15"]);
    await vi.advanceTimersByTimeAsync(100);
    expect(await found).toBe(true);
    expect(amount.scrollIntoView).toHaveBeenCalled();
  });
});
