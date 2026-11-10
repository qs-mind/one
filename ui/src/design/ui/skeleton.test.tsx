import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Skeleton } from "@/design/ui/skeleton";
import { common } from "@/texts/common";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Skeleton (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("is a still, hidden block; its container says it is loading", () => {
    renderIn(
      dir,
      <div aria-busy="true" data-testid="box">
        <span className="sr-only">{text(common.loading, lang)}</span>
        <Skeleton data-testid="block" className="h-6 w-40" />
      </div>,
    );
    const block = screen.getByTestId("block");
    expect(block.getAttribute("aria-hidden")).toBe("true");
    expect(block.className).not.toMatch(/animate-/);
    expect(block.className).toMatch(/\bbg-border\b/);
    expect(block.className).toMatch(/\brounded-lg\b/);
    expect(screen.getByTestId("box").getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText(text(common.loading, lang))).toBeTruthy();
  });
});
