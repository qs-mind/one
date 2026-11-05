// The first launch's ink check, shared: in a line that says a step worked, and beside a settings select for a moment
// after a pick there saved, so the select itself confirms the save.
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CHECK_SHOWN, InkCheck, SavedCheck } from "./InkCheck";

const check = () => document.querySelector("[data-ink-check]");

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("InkCheck", () => {
  it("is an Ink circle whose check draws itself, for the eye only", () => {
    render(<InkCheck />);
    expect(check()).toHaveAttribute("aria-hidden", "true");
    expect(check()!.querySelector("circle")).toHaveClass("fill-ink");
    expect(check()!.querySelector("path")).toHaveClass("fl-check");
  });
});

describe("SavedCheck", () => {
  it("shows nothing until a save is made, then the check for a moment", () => {
    const { rerender } = render(<SavedCheck n={0} done={false} />);
    expect(check()).toBeNull();
    rerender(<SavedCheck n={1} done />);
    expect(check()).not.toBeNull();
    act(() => void vi.advanceTimersByTime(CHECK_SHOWN));
    expect(check()).toBeNull();
    rerender(<SavedCheck n={2} done />); // the next save shows it anew
    expect(check()).not.toBeNull();
  });

  it("shows nothing for a save that failed", () => {
    const { rerender } = render(<SavedCheck n={0} done={false} />);
    rerender(<SavedCheck n={1} done={false} />);
    expect(check()).toBeNull();
  });

  it("does not show for the state it opened with", () => {
    render(<SavedCheck n={3} done />);
    expect(check()).toBeNull();
  });
});
