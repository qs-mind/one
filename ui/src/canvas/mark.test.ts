import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DUR, EASE } from "../ui/motion";
import { markFrame, STILL_MARK_MS } from "./mark";

function frame(key: string) {
  const el = document.createElement("div");
  el.dataset.frame = key;
  document.body.append(el);
  return el;
}

function reduced(on: boolean) {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: on, addEventListener() {}, removeEventListener() {} })));
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("the frame the view is sent to", () => {
  it("shows a soft Ink outline while the view glides, which fades once there", async () => {
    reduced(false);
    const el = frame("deliverable:d1");
    let finish!: () => void;
    const animate = vi.fn(() => ({ finished: new Promise<void>((resolve) => (finish = resolve)), finish() {} }));
    el.animate = animate as unknown as typeof el.animate;
    const done = markFrame("deliverable:d1", 300);
    await vi.advanceTimersByTimeAsync(0);
    expect(el.style.outline).toBe("2px solid rgb(14 15 18 / 0.45)"); // Ink, no glow, no shadow
    expect(el.style.boxShadow).toBe("");
    expect(animate).not.toHaveBeenCalled(); // still gliding
    await vi.advanceTimersByTimeAsync(300);
    expect(animate).toHaveBeenCalledWith(
      [{ outlineColor: "rgb(14 15 18 / 0.45)" }, { outlineColor: "rgb(14 15 18 / 0)" }],
      { duration: DUR.roll, easing: EASE },
    );
    finish();
    await done;
    expect(el.style.outline).toBe("");
  });

  it("with reduced motion: the outline only, still, for a moment, then gone at once", async () => {
    reduced(true);
    const el = frame("deliverable:d1");
    const animate = vi.fn();
    el.animate = animate as unknown as typeof el.animate;
    const done = markFrame("deliverable:d1", 0);
    await vi.advanceTimersByTimeAsync(0);
    expect(el.style.outline).not.toBe("");
    await vi.advanceTimersByTimeAsync(STILL_MARK_MS);
    await done;
    expect(el.style.outline).toBe("");
    expect(animate).not.toHaveBeenCalled();
  });

  it("waits for a frame the canvas draws only once the view is there", async () => {
    reduced(true);
    const done = markFrame("deliverable:d2", 0);
    await vi.advanceTimersByTimeAsync(32);
    const el = frame("deliverable:d2");
    await vi.advanceTimersByTimeAsync(32);
    expect(el.style.outline).not.toBe("");
    await vi.advanceTimersByTimeAsync(STILL_MARK_MS);
    await done;
    expect(el.style.outline).toBe("");
  });
});
