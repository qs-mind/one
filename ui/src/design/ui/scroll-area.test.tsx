import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { ScrollArea } from "@/design/ui/scroll-area";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("ScrollArea (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("the scroll area's content is reachable and its viewport rings inside", async () => {
    renderIn(
      dir,
      <ScrollArea className="h-40">
        <ul>
          {[1, 2, 3].map((n) => (
            <li key={n}>{text(surfaces.logStep, lang, { n, page: n * 4 })}</li>
          ))}
        </ul>
        <button type="button">{text(surfaces.workLog, lang)}</button>
      </ScrollArea>,
    );
    const viewport = document.querySelector('[data-slot="scroll-area-viewport"]');
    expect(viewport?.className).toMatch(/\bfocus-inset\b/);
    expect(viewport?.className).not.toMatch(/ring-|outline-none/);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    // The content stays in the Tab order (the viewport itself may be a stop when it scrolls).
    const button = screen.getByRole("button", { name: text(surfaces.workLog, lang) });
    for (let i = 0; i < 3 && document.activeElement !== button; i++) await userEvent.tab();
    expect(document.activeElement).toBe(button);
    const thumb = document.querySelector('[data-slot="scroll-area-thumb"]');
    if (thumb) expect(thumb.className).toMatch(/\bbg-line\b/);
  });
});
