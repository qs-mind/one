// Warm tooltips: the first waits about half a second; once one has shown, the next one opens at once, until 300 ms
// after the pointer left the last one.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { motion } from "./testLayout";
import { Tip, TIP_DELAY, TIP_WARM } from "./Tip";

function Bar() {
  return (
    <div role="toolbar">
      {["Zoom out", "Zoom in", "Close"].map((name) => (
        <Tip key={name} label={name}>
          <button type="button" aria-label={name}>
            •
          </button>
        </Tip>
      ))}
    </div>
  );
}

const tip = () => screen.queryByRole("tooltip", { hidden: true });
const button = (name: string) => screen.getByRole("button", { name });
const wait = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

beforeEach(() => {
  vi.useFakeTimers();
  motion(false);
});
afterEach(() => {
  wait(TIP_WARM + 1); // the group cools down, so the next test starts cold
  vi.useRealTimers();
});

describe("Tip", () => {
  it("waits about 500 ms before the first tooltip", () => {
    render(<Bar />);
    expect(TIP_DELAY).toBe(500);
    fireEvent.pointerEnter(button("Zoom in"));
    wait(TIP_DELAY - 1);
    expect(tip()).toBeNull();
    wait(1);
    expect(tip()).toHaveTextContent("Zoom in");
    expect(tip()).toHaveAttribute("aria-hidden", "true"); // the button keeps its own name; the tip is what the eye reads
    fireEvent.pointerLeave(button("Zoom in"));
    expect(tip()).toBeNull();
  });

  it("opens the neighbour at once while warm, and cold again 300 ms after leaving", () => {
    render(<Bar />);
    fireEvent.pointerEnter(button("Zoom out"));
    wait(TIP_DELAY);
    fireEvent.pointerLeave(button("Zoom out"));
    wait(TIP_WARM - 50);
    fireEvent.pointerEnter(button("Zoom in"));
    expect(tip()).toHaveTextContent("Zoom in"); // no wait: the group is warm
    fireEvent.pointerLeave(button("Zoom in"));

    wait(TIP_WARM + 1);
    fireEvent.pointerEnter(button("Close"));
    expect(tip()).toBeNull(); // cold again: the wait comes back
    wait(TIP_DELAY);
    expect(tip()).toHaveTextContent("Close");
    fireEvent.pointerLeave(button("Close"));
  });

  it("never shows when the pointer leaves before the wait is over, and leaves the group cold", () => {
    render(<Bar />);
    fireEvent.pointerEnter(button("Zoom out"));
    wait(TIP_DELAY - 100);
    fireEvent.pointerLeave(button("Zoom out"));
    wait(TIP_DELAY);
    expect(tip()).toBeNull();
    fireEvent.pointerEnter(button("Zoom in"));
    expect(tip()).toBeNull();
    fireEvent.pointerLeave(button("Zoom in"));
  });

  it("closes on a press and on Escape", () => {
    render(<Bar />);
    fireEvent.pointerEnter(button("Zoom in"));
    wait(TIP_DELAY);
    fireEvent.pointerDown(button("Zoom in"));
    expect(tip()).toBeNull();
    fireEvent.pointerLeave(button("Zoom in"));
    fireEvent.pointerEnter(button("Close"));
    expect(tip()).not.toBeNull();
    fireEvent.keyDown(button("Close"), { key: "Escape" });
    expect(tip()).toBeNull();
    fireEvent.pointerLeave(button("Close"));
  });

  it("fades in, except with reduced motion, where it simply shows", () => {
    motion(true);
    render(<Bar />);
    fireEvent.pointerEnter(button("Zoom in"));
    wait(TIP_DELAY);
    expect(tip()).not.toHaveClass("tip-in");
    fireEvent.pointerLeave(button("Zoom in"));
  });
});
