import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ARM_MS, HOLD_MS, HoldButton } from "@/design/HoldButton";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";

beforeEach(() => {
  stubBrowser();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  resetPage();
});

const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));

describe.each(DIRS)("HoldButton (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const label = text(controls.approve, lang);
  const hint = text(controls.approveHint, lang);

  function setup(props: { disabled?: boolean } = {}) {
    const onHold = vi.fn();
    renderIn(dir, <HoldButton onHold={onHold} hint={hint} {...props}>{label}</HoldButton>);
    return { onHold, button: screen.getByRole("button", { name: label }) };
  }

  it("a full hold calls onHold once; an early release does not", async () => {
    const { onHold, button } = setup();
    fireEvent.pointerDown(button, { button: 0 });
    expect(button).toHaveAttribute("data-holding");
    await wait(HOLD_MS);
    fireEvent.pointerUp(button);
    expect(onHold).toHaveBeenCalledTimes(1);
    fireEvent.pointerDown(button, { button: 0 });
    await wait(HOLD_MS - 100);
    fireEvent.pointerUp(button);
    await wait(HOLD_MS);
    expect(onHold).toHaveBeenCalledTimes(1);
    expect(button).not.toHaveAttribute("data-holding");
  });

  it("Enter and Space hold; a key repeat does not restart; the key's click is prevented", async () => {
    const { onHold, button } = setup();
    act(() => button.focus());
    for (const key of ["Enter", " "]) {
      fireEvent.keyDown(button, { key });
      await wait(HOLD_MS / 2);
      fireEvent.keyDown(button, { key, repeat: true });
      await wait(HOLD_MS / 2);
      fireEvent.keyUp(button, { key });
    }
    expect(onHold).toHaveBeenCalledTimes(2);
    const down = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    act(() => void button.dispatchEvent(down));
    expect(down.defaultPrevented).toBe(true);
    fireEvent.keyUp(button, { key: "Enter" });
  });

  it.each(["blur", "pointerLeave", "contextMenu", "pointerCancel"] as const)("%s releases", async (name) => {
    const { onHold, button } = setup();
    fireEvent.pointerDown(button, { button: 0 });
    await wait(HOLD_MS / 2);
    fireEvent[name](button);
    await wait(HOLD_MS);
    expect(onHold).not.toHaveBeenCalled();
  });

  it("disabled does not start and is announced", async () => {
    const { onHold, button } = setup({ disabled: true });
    expect(button).toBeDisabled();
    fireEvent.pointerDown(button, { button: 0 });
    await wait(HOLD_MS);
    button.click();
    button.click();
    expect(onHold).not.toHaveBeenCalled();
  });

  it("is reached by Tab, has a 44px target and describes itself", () => {
    const { button } = setup();
    act(() => button.focus());
    expect(button).toHaveFocus();
    expect(hasTarget44(button)).toBe(true);
    const help = document.getElementById(button.getAttribute("aria-describedby") ?? "");
    expect(help?.textContent).toContain(hint);
    expect(help?.textContent).toContain(text(common.holdHelpReader, lang));
  });

  it("band grows from the start side; held fill stays primary", () => {
    const { button } = setup();
    const band = button.querySelector('[data-slot="hold-band"]');
    expect(band).toHaveAttribute("aria-hidden", "true");
    expect(band?.getAttribute("class")).toMatch(/\bstart-0\b/);
    expect(band?.getAttribute("class")).toMatch(/\bbg-hold\b/);
    expect(button.getAttribute("class")).toContain("data-holding:bg-primary!");
    expect(button.getAttribute("class")).not.toContain("primary-pressed");
  });

  it("an early release opens the hint", async () => {
    const { button } = setup();
    expect(screen.queryByText(text(common.holdToConfirm, lang))).toBeNull();
    fireEvent.pointerDown(button, { button: 0 });
    await wait(200);
    fireEvent.pointerUp(button);
    expect(screen.getByText(text(common.holdToConfirm, lang))).toBeInTheDocument();
  });

  it("assistive path: one click arms, a second within 5s goes ahead once", async () => {
    const { onHold, button } = setup();
    const pressAgain = text(common.pressAgain, lang);
    act(() => button.click());
    expect(onHold).not.toHaveBeenCalled();
    expect(button).toHaveAttribute("data-armed");
    const live = document.querySelector('[aria-live="polite"]');
    expect(live?.textContent).toBe(pressAgain);
    expect(button).toHaveTextContent(pressAgain);
    await wait(ARM_MS - 1000);
    act(() => button.click());
    expect(onHold).toHaveBeenCalledTimes(1);
    expect(button).not.toHaveAttribute("data-armed");
    expect(button).toHaveTextContent(label);
  });

  it("after 5s the arm lapses and a click arms again", async () => {
    const { onHold, button } = setup();
    act(() => button.click());
    await wait(ARM_MS);
    expect(button).not.toHaveAttribute("data-armed");
    act(() => button.click());
    expect(onHold).not.toHaveBeenCalled();
    expect(button).toHaveAttribute("data-armed");
  });

  it("a pointer click never arms", () => {
    const { button } = setup();
    fireEvent.click(button, { detail: 1 });
    expect(button).not.toHaveAttribute("data-armed");
  });
});
