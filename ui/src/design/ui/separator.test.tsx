import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Separator } from "@/design/ui/separator";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Separator (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("the separator is a 1px hairline in --border, passive", () => {
    renderIn(
      dir,
      <div className="flex items-center gap-4">
        <Separator className="flex-1 data-horizontal:w-auto" />
        <span className="text-xs text-muted-foreground">{text(surfaces.or, lang)}</span>
        <Separator className="flex-1 data-horizontal:w-auto" />
      </div>,
    );
    const lines = screen.getAllByRole("separator");
    expect(lines).toHaveLength(2);
    for (const line of lines) {
      expect(line.className).toMatch(/\bbg-border\b/);
      expect(line.className).toMatch(/data-horizontal:h-px/);
      expect(line.hasAttribute("tabindex")).toBe(false);
    }
  });
});
