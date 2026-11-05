import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AutoHeight } from "./AutoHeight";
import { DUR, EASE } from "./motion";

// The content's size, as a ResizeObserver reports it (jsdom has no layout).
let report: ((height: number) => void) | undefined;
class Watch {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe(target: Element) {
    report = (height) => {
      const box = [{ inlineSize: 400, blockSize: height }];
      const entry = { target, contentRect: new DOMRect(0, 0, 400, height), borderBoxSize: box } as unknown as ResizeObserverEntry;
      act(() => this.callback([entry], this as unknown as ResizeObserver));
    };
  }
  unobserve() {}
  disconnect() {}
}

let animate: ReturnType<typeof vi.fn>;
let end: () => void;

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", Watch);
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  animate = vi.fn(() => {
    const finished = new Promise<void>((resolve) => (end = resolve));
    return { finished, finish: () => end(), cancel: () => end() };
  });
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
});
afterEach(() => {
  delete (Element.prototype as { animate?: unknown }).animate;
  report = undefined;
});

describe("AutoHeight", () => {
  it("shows its content at its own height at first, with no motion", () => {
    const { getByText } = render(<AutoHeight>one step</AutoHeight>);
    report!(120);
    expect(getByText("one step")).toBeInTheDocument();
    expect(animate).not.toHaveBeenCalled();
  });

  it("eases from the old height to the new one when the content changes size, clipping only while it moves", async () => {
    const { container } = render(<AutoHeight>content</AutoHeight>);
    report!(120);
    report!(200);
    expect(animate).toHaveBeenCalledTimes(1);
    expect(animate).toHaveBeenCalledWith([{ height: "120px" }, { height: "200px" }], expect.objectContaining({ duration: DUR.base, easing: EASE }));
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.style.overflow).toBe("clip");
    await act(async () => {
      end();
      await Promise.resolve();
    });
    expect(outer.style.overflow).toBe(""); // focus rings at the edges show again
  });

  it("with reduced motion, takes the new height at once", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    render(<AutoHeight>content</AutoHeight>);
    report!(120);
    report!(200);
    expect(animate).not.toHaveBeenCalled();
  });

  it("the same height again does not move", () => {
    render(<AutoHeight>content</AutoHeight>);
    report!(120);
    report!(120);
    expect(animate).not.toHaveBeenCalled();
  });
});
