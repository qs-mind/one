import { act, render } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AutoHeight } from "./AutoHeight";
import { DUR, EASE } from "./motion";

// The content's height, as layout would give it (jsdom has none): each line is 30 px.
const LINE = 30;
function layout() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const lines = this.querySelectorAll("p").length;
    return new DOMRect(0, 0, 400, lines * LINE);
  });
}

let animate: ReturnType<typeof vi.fn>;
let end: () => void;

function reduced(on: boolean) {
  vi.stubGlobal("matchMedia", () => ({ matches: on, addEventListener() {}, removeEventListener() {} }));
}

/** A card whose lines the test adds, as a step adds its feedback line. */
let setLines: (n: number) => void;
function Card({ start = 1 }: { start?: number }) {
  const [lines, set] = useState(start);
  setLines = set;
  return (
    <AutoHeight>
      {Array.from({ length: lines }, (_, i) => (
        <p key={i}>line {i}</p>
      ))}
    </AutoHeight>
  );
}

async function lines(n: number) {
  await act(async () => {
    setLines(n);
    await Promise.resolve(); // the mutation is seen as a microtask, before the frame is drawn
  });
}

beforeEach(() => {
  reduced(false);
  layout();
  animate = vi.fn(() => {
    const finished = new Promise<void>((resolve) => (end = resolve));
    return { finished, finish: () => end(), cancel: () => end() };
  });
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
});
afterEach(() => {
  delete (Element.prototype as { animate?: unknown }).animate;
});

describe("AutoHeight", () => {
  it("shows its content at its own height at first, with no motion", () => {
    const { getByText } = render(<Card />);
    expect(getByText("line 0")).toBeInTheDocument();
    expect(animate).not.toHaveBeenCalled();
  });

  it("eases from the old height to the new one when the content changes, clipping only while it moves", async () => {
    const { container } = render(<Card />);
    await lines(3);
    expect(animate).toHaveBeenCalledTimes(1);
    expect(animate).toHaveBeenCalledWith([{ height: "30px" }, { height: "90px" }], expect.objectContaining({ duration: DUR.base, easing: EASE }));
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.style.overflow).toBe("clip");
    await act(async () => {
      end();
      await Promise.resolve();
    });
    expect(outer.style.overflow).toBe(""); // focus rings at the edges show again
  });

  it("eases back down when a line goes", async () => {
    render(<Card start={3} />);
    await lines(1);
    expect(animate).toHaveBeenCalledWith([{ height: "90px" }, { height: "30px" }], expect.anything());
  });

  it("with reduced motion, takes the new height at once", async () => {
    reduced(true);
    render(<Card />);
    await lines(3);
    expect(animate).not.toHaveBeenCalled();
  });

  it("a change that keeps the height does not move", async () => {
    const { getByText } = render(<Card />);
    await act(async () => {
      getByText("line 0").textContent = "the same line, other words";
      await Promise.resolve();
    });
    expect(animate).not.toHaveBeenCalled();
  });

  it("starts the motion outside the ResizeObserver's turn, so no observer loop is reported", async () => {
    const observed: ResizeObserverCallback[] = [];
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: ResizeObserverCallback) {
          observed.push(callback);
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    render(<Card />);
    // a size the observer reports (the window narrowed, a font came): noted, never animated from its callback
    act(() => observed.forEach((callback) => callback([], {} as ResizeObserver)));
    expect(animate).not.toHaveBeenCalled();
  });
});
