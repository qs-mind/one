import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DUR } from "./motion";
import { RollingNumber } from "./RollingNumber";

type Call = { el: Element; keyframes: Keyframe[]; options: KeyframeAnimationOptions; end: () => void };
let calls: Call[] = [];

/** Web Animations in jsdom: each call is kept, and ends when the test says. */
function fakeAnimate() {
  calls = [];
  const animate = vi.fn(function (this: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
    let end = () => {};
    const finished = new Promise<void>((resolve) => (end = resolve));
    calls.push({ el: this, keyframes, options, end });
    return { finished, finish: end, cancel: end } as unknown as Animation;
  });
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
  return animate;
}

function reduced(on: boolean) {
  vi.stubGlobal("matchMedia", () => ({ matches: on, addEventListener() {}, removeEventListener() {} }));
}

async function endAll() {
  await act(async () => {
    for (const call of calls) call.end();
    await Promise.resolve();
  });
}

/** What the face ends on: the visible face without the old digits rolling out, or the plain text at rest. */
function shown(box: HTMLElement) {
  const face = (box.querySelector("[aria-hidden='true']") ?? box).cloneNode(true) as HTMLElement;
  for (const old of face.querySelectorAll("[data-roll-from]")) old.remove();
  return face.textContent;
}

beforeEach(() => reduced(false));
afterEach(() => {
  delete (Element.prototype as { animate?: unknown }).animate;
});

describe("RollingNumber", () => {
  it("shows the value still on first render", () => {
    const animate = fakeAnimate();
    const { container } = render(<RollingNumber text="4,859,830.00" />);
    expect(container.textContent).toBe("4,859,830.00");
    expect(animate).not.toHaveBeenCalled();
  });

  it("on a change, rolls only the digits that changed, then rests on the new text", async () => {
    fakeAnimate();
    const { container, rerender } = render(<RollingNumber text="4,859,830.00" />);
    rerender(<RollingNumber text="4,861,330.00" />);
    // 5→6, 9→1 and 8→3 change: each rolls its old digit out and its new one in; commas and the rest stay
    const rolled = new Set(calls.map((call) => call.el.closest("[data-roll]")));
    expect(rolled.size).toBe(3);
    expect(calls.every((call) => call.options.duration === DUR.roll)).toBe(true);
    expect(shown(container)).toBe("4,861,330.00");
    await endAll();
    expect(container.textContent).toBe("4,861,330.00");
    expect(container.querySelector("[data-roll-from]")).toBeNull();
  });

  it("a rising value rolls up, a falling one down", () => {
    fakeAnimate();
    const { rerender } = render(<RollingNumber text="120" />);
    rerender(<RollingNumber text="130" />);
    const rising = calls.find((call) => call.el.hasAttribute("data-roll-to"))!;
    expect(rising.keyframes[0]!.transform).toBe("translateY(100%)");
    calls = [];
    rerender(<RollingNumber text="110" />);
    const falling = calls.find((call) => call.el.hasAttribute("data-roll-to"))!;
    expect(falling.keyframes[0]!.transform).toBe("translateY(-100%)");
  });

  it("RF4: two changes 100 ms apart end on the second value, never the middle one", async () => {
    vi.useFakeTimers();
    try {
      fakeAnimate();
      const { container, rerender } = render(<RollingNumber text="1,000.00" />);
      rerender(<RollingNumber text="1,250.00" />);
      act(() => void vi.advanceTimersByTime(100));
      rerender(<RollingNumber text="1,400.00" />);
      expect(shown(container)).toBe("1,400.00");
      // the first roll ending late does not bring the middle value back
      await act(async () => {
        calls[0]!.end();
        await Promise.resolve();
      });
      expect(shown(container)).toBe("1,400.00");
      await endAll();
      expect(container.textContent).toBe("1,400.00");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the digits and separators the locale uses (ar-EG)", async () => {
    fakeAnimate();
    const format = new Intl.NumberFormat("ar-EG", { minimumFractionDigits: 2 });
    const { container, rerender } = render(<RollingNumber text={format.format(4859830)} />);
    rerender(<RollingNumber text={format.format(4861330)} />);
    expect(calls.length).toBeGreaterThan(0);
    expect(shown(container)).toBe(format.format(4861330));
    await endAll();
    expect(container.textContent).toBe(format.format(4861330));
  });

  it("while it rolls, the figures keep their left-to-right order in Arabic text, and the words stay whole", () => {
    // a rolling digit is a box, which the bidi algorithm reads as a neutral: beside Arabic words "1.8" would show
    // as "8.1". The figures sit in one left-to-right isolate, each in a box of its own; the words are never split.
    fakeAnimate();
    const { container, rerender } = render(<RollingNumber text={"\u200f1.8 مليون ج.م.\u200f"} />);
    rerender(<RollingNumber text={"\u200f1.9 مليون ج.م.\u200f"} />);
    const face = container.querySelector("[aria-hidden='true']")!;
    const figures = face.querySelector("bdi[dir='ltr']");
    expect(figures).not.toBeNull();
    const boxes = [...figures!.children];
    expect(boxes.map((el) => el.querySelector("[data-roll-to]")?.textContent ?? el.textContent)).toEqual(["1", ".", "9"]);
    expect(boxes.every((el) => el.classList.contains("inline-block") || el.hasAttribute("data-roll"))).toBe(true);
    expect(face.textContent).toContain(" مليون ج.م.");
    expect([...face.querySelectorAll("span")].some((el) => el.textContent === "م")).toBe(false);
  });

  it("while it rolls, a screen reader gets the final text only", () => {
    fakeAnimate();
    const { container, rerender } = render(<RollingNumber text="120" />);
    rerender(<RollingNumber text="130" />);
    expect(container.querySelector(".sr-only")?.textContent).toBe("130");
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull();
  });

  it("with reduced motion, the text swaps at once", () => {
    reduced(true);
    const animate = fakeAnimate();
    const { container, rerender } = render(<RollingNumber text="120" />);
    rerender(<RollingNumber text="130" />);
    expect(animate).not.toHaveBeenCalled();
    expect(container.textContent).toBe("130");
  });
});
