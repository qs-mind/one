// A progress bar only ever shows real counts: «212 of 480 files» fills 212/480 of it (scaleX, from the side the
// words start on). With no count behind it there is no bar at all: never a sweep, never a made-up share.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressBar } from "./ProgressBar";
import { motion } from "./testLayout";

const fill = () => document.querySelector<HTMLElement>("[data-progress-fill]");

describe("ProgressBar", () => {
  it("fills by the real share, with transform only", () => {
    motion(false);
    const { rerender } = render(<ProgressBar done={212} total={480} />);
    expect(fill()!.style.transform).toBe(`scaleX(${212 / 480})`);
    expect(fill()!.style.width).toBe("");
    rerender(<ProgressBar done={480} total={480} />);
    expect(fill()!.style.transform).toBe("scaleX(1)");
  });

  it("shows nothing without a real count", () => {
    motion(false);
    for (const [done, total] of [
      [0, 0],
      [3, Number.NaN],
      [Number.NaN, 10],
      [-1, 10],
      [1, -5],
      [1, Number.POSITIVE_INFINITY],
    ]) {
      const { container, unmount } = render(<ProgressBar done={done!} total={total!} />);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });

  it("never runs past the end", () => {
    motion(false);
    render(<ProgressBar done={600} total={480} />);
    expect(fill()!.style.transform).toBe("scaleX(1)");
  });

  it("is for the eye: the line beside it says the numbers", () => {
    motion(false);
    const { container } = render(<ProgressBar done={1} total={2} />);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });

  it("with reduced motion jumps to the new share", () => {
    motion(true);
    render(<ProgressBar done={1} total={2} />);
    expect(fill()).toHaveAttribute("data-still");
  });
});
