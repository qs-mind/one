import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DUR, EASE, play, reducedMotion, useReducedMotion } from "./motion";

type Listener = (event: { matches: boolean }) => void;

/** A fake `prefers-reduced-motion` query the test can flip. */
function motionQuery(reduced: boolean) {
  const listeners = new Set<Listener>();
  const query = {
    matches: reduced,
    addEventListener: (_: string, listener: Listener) => void listeners.add(listener),
    removeEventListener: (_: string, listener: Listener) => void listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    set(next: boolean) {
      query.matches = next;
      for (const listener of listeners) listener({ matches: next });
    },
  };
}

function fakeElement() {
  const animation = { finished: Promise.resolve(), finish: vi.fn() };
  const el = { animate: vi.fn(() => animation) } as unknown as Element & { animate: ReturnType<typeof vi.fn> };
  return { el, animation };
}

afterEach(() => vi.unstubAllGlobals());

describe("motion", () => {
  it("keeps the timings and the ease ONE already uses", () => {
    expect(EASE).toBe("cubic-bezier(0.2, 0.8, 0.2, 1)");
    expect(DUR).toEqual({ short: 150, base: 220, long: 300, roll: 400 });
  });

  it("reads reduced motion from the system, and is off where the query is missing", () => {
    motionQuery(true);
    expect(reducedMotion()).toBe(true);
    vi.stubGlobal("matchMedia", undefined);
    expect(reducedMotion()).toBe(false);
  });

  it("plays with the calm ease and the given time", async () => {
    motionQuery(false);
    const { el } = fakeElement();
    await play(el, [{ opacity: 0 }, { opacity: 1 }], DUR.base);
    expect(el.animate).toHaveBeenCalledWith([{ opacity: 0 }, { opacity: 1 }], expect.objectContaining({ duration: 220, easing: EASE }));
  });

  it("with reduced motion, nothing plays and it ends at once", async () => {
    motionQuery(true);
    const { el } = fakeElement();
    await play(el, [{ opacity: 0 }, { opacity: 1 }], DUR.base);
    expect(el.animate).not.toHaveBeenCalled();
  });

  it("ends at once where the browser cannot animate", async () => {
    motionQuery(false);
    await expect(play({} as Element, [{ opacity: 1 }], DUR.short)).resolves.toBeUndefined();
  });

  it("reduced motion turned on while something plays finishes it at once (RF1)", () => {
    const query = motionQuery(false);
    const animation = { finished: new Promise<void>(() => undefined), finish: vi.fn() };
    const el = { animate: vi.fn(() => animation) } as unknown as Element;
    void play(el, [{ opacity: 0 }, { opacity: 1 }], DUR.long);
    query.set(true);
    expect(animation.finish).toHaveBeenCalled();
  });

  it("useReducedMotion follows the system as it changes", () => {
    const query = motionQuery(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
    act(() => query.set(true));
    expect(result.current).toBe(true);
  });
});
