// Three dots fading in turn: the only sign of a job that really runs but has no count to show. Opacity only; with
// reduced motion there are none (the words beside them say it runs).
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { motion } from "./testLayout";
import { WorkDots } from "./WorkDots";

describe("WorkDots", () => {
  it("is three dots, for the eye only", () => {
    motion(false);
    const { container } = render(<WorkDots />);
    const dots = container.querySelector("[data-dots]")!;
    expect(dots).toHaveAttribute("aria-hidden", "true");
    expect(dots).toHaveClass("work-dots");
    expect(dots.children).toHaveLength(3);
  });

  it("shows none with reduced motion", () => {
    motion(true);
    const { container } = render(<WorkDots />);
    expect(container).toBeEmptyDOMElement();
  });
});
