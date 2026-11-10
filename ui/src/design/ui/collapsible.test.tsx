import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChevronDownIcon } from "lucide-react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Button } from "@/design/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/design/ui/collapsible";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Collapsible (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: { en: string; ar: string }) => text(pair, lang);

  function renderCollapsible() {
    return renderIn(
      dir,
      <Collapsible>
        <CollapsibleTrigger render={<Button variant="ghost" className="justify-start gap-2 px-2" />}>
          <ChevronDownIcon aria-hidden className="size-4.5 group-data-panel-open/button:rotate-180" />
          {t(surfaces.details)}
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2">{t(surfaces.detailsBody)}</CollapsibleContent>
      </Collapsible>,
    );
  }

  it("is a 44px trigger, closed at first, its panel out of the page", () => {
    renderCollapsible();
    const trigger = screen.getByRole("button", { name: t(surfaces.details) });
    expect(hasTarget44(trigger)).toBe(true);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText(t(surfaces.detailsBody))).toBeNull();
  });

  it("Enter and Space toggle it; aria-expanded follows and points at the panel", async () => {
    renderCollapsible();
    const trigger = screen.getByRole("button", { name: t(surfaces.details) });
    await userEvent.tab();
    expect(document.activeElement).toBe(trigger);
    await userEvent.keyboard("{Enter}");
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const panel = screen.getByText(t(surfaces.detailsBody));
    expect(trigger.getAttribute("aria-controls")).toBe(panel.id);
    await userEvent.keyboard(" ");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText(t(surfaces.detailsBody))).toBeNull();
  });
});
