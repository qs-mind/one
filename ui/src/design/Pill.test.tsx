import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Pill } from "@/design/Pill";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Pill (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("is a passive label: no role, not focusable, drawn by tokens", async () => {
    renderIn(dir, <Pill>{text(common.sample, lang)}</Pill>);
    const pill = screen.getByText(text(common.sample, lang));
    expect(pill.tagName).toBe("SPAN");
    expect(pill).not.toHaveAttribute("role");
    expect(pill).not.toHaveAttribute("tabindex");
    await userEvent.tab();
    expect(pill).not.toHaveFocus();
    expect(document.body).toHaveFocus();
    expect(pill.getAttribute("class")?.split(/\s+/)).toEqual(
      expect.arrayContaining(["h-7", "rounded-full", "border-line", "text-xs", "text-muted-foreground"]),
    );
  });
});
