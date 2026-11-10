import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Button } from "@/design/ui/button";
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/design/ui/popover";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Popover (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: { en: string; ar: string }) => text(pair, lang);

  function renderPopover(side?: "inline-end" | "bottom") {
    return renderIn(
      dir,
      <Popover>
        <PopoverTrigger render={<Button variant="outline" />}>{t(surfaces.workLog)}</PopoverTrigger>
        <PopoverContent side={side}>
          <PopoverHeader>
            <PopoverTitle>{t(surfaces.workLogTitle)}</PopoverTitle>
            <PopoverDescription>{t(surfaces.workLogBody)}</PopoverDescription>
          </PopoverHeader>
        </PopoverContent>
      </Popover>,
    );
  }

  it("opens on click and closes on Escape; the trigger is a 44px target", async () => {
    renderPopover();
    const trigger = screen.getByRole("button", { name: t(surfaces.workLog) });
    expect(hasTarget44(trigger)).toBe(true);
    await userEvent.click(trigger);
    const title = await screen.findByText(t(surfaces.workLogTitle));
    expect(title.className).toMatch(/font-bold/);
    expect(screen.getByText(t(surfaces.workLogBody)).className).toMatch(/text-xs/);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText(t(surfaces.workLogTitle))).toBeNull());
  });

  it("opens from the keyboard", async () => {
    renderPopover();
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: t(surfaces.workLog) }));
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByText(t(surfaces.workLogTitle))).toBeTruthy();
  });

  it.each(["inline-end", "bottom"] as const)("keeps the logical side %s and the surface tokens", async (side) => {
    renderPopover(side);
    await userEvent.click(screen.getByRole("button", { name: t(surfaces.workLog) }));
    await screen.findByText(t(surfaces.workLogTitle));
    const popup = document.querySelector('[data-slot="popover-content"]');
    expect(popup?.getAttribute("data-side")).toBe(side);
    expect(popup?.className).toMatch(/rounded-2xl/);
    expect(popup?.className).toMatch(/border-line/);
    expect(popup?.className).not.toMatch(/shadow|ring-|duration-/);
  });
});
