import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DUR, EASE } from "./motion";
import { centreOf, withTransition } from "./viewTransition";

type Listener = () => void;

function reducedMotion(on: boolean) {
  const listeners = new Set<Listener>();
  const query = {
    matches: on,
    addEventListener: (_: string, listener: Listener) => void listeners.add(listener),
    removeEventListener: (_: string, listener: Listener) => void listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    turnOn() {
      query.matches = true;
      for (const listener of listeners) listener();
    },
  };
}

/** A fake View Transitions API: runs the update at once, like the browser does after it takes the old picture. */
function viewTransitions() {
  let finish!: () => void;
  const transition = {
    ready: Promise.resolve(),
    finished: new Promise<void>((resolve) => (finish = resolve)),
    updateCallbackDone: Promise.resolve(),
    skipTransition: vi.fn(() => finish()),
  };
  const start = vi.fn((update: () => void) => {
    update();
    return transition;
  });
  Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
  return { start, transition, finish: () => finish() };
}

const animate = vi.fn(() => ({ finished: Promise.resolve(), finish: vi.fn() }));

beforeEach(() => {
  reducedMotion(false);
  document.body.innerHTML = '<div id="root"></div>';
  Element.prototype.animate = animate as unknown as Element["animate"];
  animate.mockClear();
  vi.stubGlobal("innerWidth", 1440);
  vi.stubGlobal("innerHeight", 900);
});

afterEach(() => {
  delete (document as { startViewTransition?: unknown }).startViewTransition;
  delete (Element.prototype as { animate?: unknown }).animate;
  document.documentElement.dir = "";
});

describe("withTransition", () => {
  it("with View Transitions: the update runs inside one, and the new page is revealed by a circle from the origin", async () => {
    const { start, finish } = viewTransitions();
    const update = vi.fn();
    const done = withTransition(update, { x: 1300, y: 28 });
    expect(start).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
    await Promise.resolve();
    await Promise.resolve();
    expect(animate).toHaveBeenCalledWith(
      { clipPath: ["circle(0px at 1300px 28px)", `circle(${Math.hypot(1300, 900 - 28)}px at 1300px 28px)`] },
      expect.objectContaining({ duration: DUR.long, easing: EASE, pseudoElement: "::view-transition-new(root)" }),
    );
    expect(document.documentElement.classList.contains("lang-wipe")).toBe(true);
    finish();
    await done;
    expect(document.documentElement.classList.contains("lang-wipe")).toBe(false);
  });

  it("without an origin, the circle grows from the middle of the window", async () => {
    const { finish } = viewTransitions();
    const done = withTransition(() => {});
    await Promise.resolve();
    await Promise.resolve();
    expect(animate).toHaveBeenCalledWith(
      { clipPath: ["circle(0px at 720px 450px)", `circle(${Math.hypot(720, 450)}px at 720px 450px)`] },
      expect.anything(),
    );
    finish();
    await done;
  });

  it("without View Transitions: the update runs and the page cross-fades once", async () => {
    const update = vi.fn();
    await withTransition(update, { x: 10, y: 10 });
    expect(update).toHaveBeenCalledTimes(1);
    expect(animate).toHaveBeenCalledTimes(1);
    expect(animate.mock.contexts[0]).toBe(document.getElementById("root"));
    expect(animate).toHaveBeenCalledWith([{ opacity: 0 }, { opacity: 1 }], expect.objectContaining({ duration: DUR.short }));
  });

  it("with reduced motion: only the update, no transition and no animation", async () => {
    reducedMotion(true);
    const { start } = viewTransitions();
    const update = vi.fn();
    await withTransition(update, { x: 10, y: 10 });
    expect(update).toHaveBeenCalledTimes(1);
    expect(start).not.toHaveBeenCalled();
    expect(animate).not.toHaveBeenCalled();
  });

  it("RF1: reduced motion turned on mid-wipe skips to the new page at once", async () => {
    const query = reducedMotion(false);
    const { transition } = viewTransitions();
    const done = withTransition(() => {}, { x: 10, y: 10 });
    query.turnOn();
    expect(transition.skipTransition).toHaveBeenCalled();
    await done;
  });

  it("RF3: on an Arabic page the origin is the button's own centre, not mirrored", () => {
    document.documentElement.dir = "rtl";
    const button = document.createElement("button");
    document.body.append(button);
    button.getBoundingClientRect = () => new DOMRect(1200, 12, 80, 32);
    expect(centreOf(button)).toEqual({ x: 1240, y: 28 });
  });
});
