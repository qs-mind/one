import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Button } from "@/design/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/design/ui/tooltip";
import { common } from "@/texts/common";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Tooltip (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const name = text(common.settings, lang);

  it("shows on focus, on the logical inline-end side, in the inverted bubble", async () => {
    renderIn(
      dir,
      <Tooltip>
        <TooltipTrigger render={<Button size="icon" variant="ghost" aria-label={name} />} />
        <TooltipContent side="inline-end">{name}</TooltipContent>
      </Tooltip>,
    );
    const trigger = screen.getByRole("button", { name });
    expect(hasTarget44(trigger)).toBe(true);
    await userEvent.tab();
    expect(trigger).toHaveFocus();
    const bubble = await screen.findByText(name, { selector: "[data-slot=tooltip-content]" });
    expect(bubble.closest("[data-side]")).toHaveAttribute("data-side", "inline-end");
    expect(bubble.getAttribute("class")).toMatch(/\bbg-foreground\b/);
    expect(bubble.getAttribute("class")).toMatch(/\btext-background\b/);
  });
});
