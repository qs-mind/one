// Press-and-hold for anything that costs money or can't be taken back: it fires only after a full hold (about 900 ms),
// by pointer or by holding Enter or Space; released early it does nothing.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HOLD_MS, HoldButton } from "./HoldButton";

function motion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

function setup() {
  const onHold = vi.fn();
  render(
    <HoldButton onHold={onHold} hint="اضغط مطوّل عشان تكمّل: ده بيكلّف فلوس.">
      ابدأ التكليف
    </HoldButton>,
  );
  return { onHold, button: screen.getByRole("button", { name: "ابدأ التكليف" }) };
}

beforeEach(() => {
  vi.useFakeTimers();
  motion(false);
});
afterEach(() => vi.useRealTimers());

describe("HoldButton", () => {
  it("holds for about 900 ms", () => expect(HOLD_MS).toBe(900));

  it("does not fire when released early", () => {
    const { onHold, button } = setup();
    fireEvent.pointerDown(button, { button: 0 });
    vi.advanceTimersByTime(HOLD_MS - 100);
    fireEvent.pointerUp(button);
    vi.advanceTimersByTime(2000);
    expect(onHold).not.toHaveBeenCalled();
  });

  it("does not fire when the pointer leaves or the press is cancelled", () => {
    const { onHold, button } = setup();
    fireEvent.pointerDown(button, { button: 0 });
    fireEvent.pointerLeave(button);
    fireEvent.pointerDown(button, { button: 0 });
    fireEvent.pointerCancel(button);
    vi.advanceTimersByTime(2000);
    expect(onHold).not.toHaveBeenCalled();
  });

  it("fires once on a full hold", () => {
    const { onHold, button } = setup();
    fireEvent.pointerDown(button, { button: 0 });
    vi.advanceTimersByTime(HOLD_MS);
    fireEvent.pointerUp(button);
    expect(onHold).toHaveBeenCalledTimes(1);
  });

  it("a plain click does nothing", () => {
    const { onHold, button } = setup();
    fireEvent.click(button);
    fireEvent.keyDown(button, { key: "Enter" });
    fireEvent.keyUp(button, { key: "Enter" });
    vi.advanceTimersByTime(2000);
    expect(onHold).not.toHaveBeenCalled();
  });

  it("works by keyboard: holding Enter or Space, and a key repeat does not restart it", () => {
    const { onHold, button } = setup();
    fireEvent.keyDown(button, { key: " " });
    vi.advanceTimersByTime(500);
    fireEvent.keyDown(button, { key: " ", repeat: true });
    vi.advanceTimersByTime(HOLD_MS - 500);
    expect(onHold).toHaveBeenCalledTimes(1);
    fireEvent.keyUp(button, { key: " " });
    fireEvent.keyDown(button, { key: "Enter" });
    vi.advanceTimersByTime(HOLD_MS);
    expect(onHold).toHaveBeenCalledTimes(2);
  });

  it("a key released early does nothing, nor a right-click", () => {
    const { onHold, button } = setup();
    fireEvent.keyDown(button, { key: "Enter" });
    vi.advanceTimersByTime(300);
    fireEvent.keyUp(button, { key: "Enter" });
    fireEvent.pointerDown(button, { button: 2 });
    vi.advanceTimersByTime(2000);
    expect(onHold).not.toHaveBeenCalled();
  });

  it("tells screen readers how it works", () => {
    const { button } = setup();
    expect(button).toHaveAccessibleDescription("اضغط مطوّل عشان تكمّل: ده بيكلّف فلوس.");
  });

  it("with reduced motion it still needs the full hold (a safety delay, not motion), with no fill", () => {
    motion(true);
    const animate = vi.fn();
    Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
    const { onHold, button } = setup();
    fireEvent.pointerDown(button, { button: 0 });
    vi.advanceTimersByTime(HOLD_MS - 1);
    expect(onHold).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onHold).toHaveBeenCalledTimes(1);
    expect(animate).not.toHaveBeenCalled();
  });
});
