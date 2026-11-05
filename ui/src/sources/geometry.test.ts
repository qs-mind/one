import { afterEach, describe, expect, it } from "vitest";
import { linePath, markPath, visibleRect } from "./geometry";

function box(rect: DOMRect, style: Partial<CSSStyleDeclaration> = {}, parent: HTMLElement = document.body) {
  const el = document.createElement("div");
  Object.assign(el.style, style);
  el.getBoundingClientRect = () => rect;
  parent.append(el);
  return el;
}

afterEach(() => (document.body.innerHTML = ""));

describe("what is on screen", () => {
  it("an element inside the window is on screen", () => {
    const el = box(new DOMRect(10, 10, 100, 20));
    expect(visibleRect(el)).toEqual(new DOMRect(10, 10, 100, 20));
  });

  it("an element outside the window, or with no size, is not", () => {
    expect(visibleRect(box(new DOMRect(10, innerHeight + 5, 100, 20)))).toBeNull();
    expect(visibleRect(box(new DOMRect(-200, 10, 100, 20)))).toBeNull();
    expect(visibleRect(box(new DOMRect(10, 10, 0, 0)))).toBeNull();
  });

  it("an element scrolled out of its scroll box is not on screen, though it is inside the window", () => {
    const scroller = box(new DOMRect(0, 0, 300, 200), { overflow: "auto" });
    const inside = box(new DOMRect(10, 250, 100, 20), {}, scroller);
    expect(visibleRect(inside)).toBeNull();
    const shown = box(new DOMRect(10, 190, 100, 20), {}, scroller);
    expect(visibleRect(shown)).toEqual(new DOMRect(10, 190, 100, 10)); // cut to the part showing
  });

  it("a detached element is not on screen", () => {
    const el = document.createElement("div");
    el.getBoundingClientRect = () => new DOMRect(10, 10, 100, 20);
    expect(visibleRect(el)).toBeNull();
  });
});

describe("the source line", () => {
  it("runs from the number's facing side to the source's facing side", () => {
    const number = new DOMRect(500, 100, 60, 20); // the source is to its left (as from an Arabic chat)
    const source = new DOMRect(100, 300, 200, 40);
    const d = linePath(number, source);
    expect(d.startsWith("M 500 110 ")).toBe(true); // the number's left edge, middle
    expect(d.endsWith(" 300 320")).toBe(true); // the source's right edge, middle
  });

  it("flips with the positions, not the language", () => {
    const d = linePath(new DOMRect(100, 100, 60, 20), new DOMRect(400, 300, 200, 40));
    expect(d.startsWith("M 160 110 ")).toBe(true);
    expect(d.endsWith(" 400 320")).toBe(true);
  });

  it("goes up or down when the two overlap side to side, gently curved", () => {
    const d = linePath(new DOMRect(100, 100, 60, 20), new DOMRect(80, 300, 200, 40));
    expect(d).toMatch(/^M 130 120 C /); // the number's bottom middle
    expect(d.endsWith(" 180 300")).toBe(true); // the source's top middle
  });
});

describe("the source mark", () => {
  const figure = new DOMRect(100, 50, 80, 20);

  it("a box starts at the inline-start top corner: left in English", () => {
    expect(markPath(figure, "box", "ltr").startsWith("M 97 47 ")).toBe(true);
  });

  it("flips in Arabic: it starts at the right and runs leftwards first", () => {
    const d = markPath(figure, "box", "rtl");
    expect(d.startsWith("M 183 47 H 97 ")).toBe(true);
  });

  it("an underline runs from inline-start to inline-end under the figure", () => {
    expect(markPath(figure, "underline", "ltr")).toBe("M 100 72 H 180");
    expect(markPath(figure, "underline", "rtl")).toBe("M 180 72 H 100");
  });
});
