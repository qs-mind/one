import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HouseIcon, LayersIcon, SettingsIcon } from "lucide-react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Rail, type RailItem } from "@/design/Rail";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Rail (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: { en: string; ar: string }) => text(pair, lang);

  function renderRail(onSelect = vi.fn()) {
    const items: RailItem[] = [
      { id: "home", label: t(common.home), icon: HouseIcon, current: true, render: <a href="#/home" /> },
      { id: "tenders", label: t(common.tenders), icon: LayersIcon, onSelect },
    ];
    const footer: RailItem[] = [{ id: "settings", label: t(common.settings), icon: SettingsIcon, onSelect }];
    return { onSelect, ...renderIn(dir, <Rail label={t(common.navigation)} items={items} footerItems={footer} />) };
  }

  it("is a nav named in words, with the wordmark first and items in DOM order", () => {
    renderRail();
    const nav = screen.getByRole("navigation", { name: t(common.navigation) });
    expect(nav.firstElementChild?.textContent).toBe("ONE");
    const names = [...nav.querySelectorAll("a, button")].map((el) => el.getAttribute("aria-label"));
    expect(names).toEqual([t(common.home), t(common.tenders), t(common.settings)]);
    expect(nav.className).toMatch(/w-\(--rail-w\)/);
    expect(nav.className).toMatch(/\bbg-muted\b/);
  });

  it("each item is a 48px named target; only the current one has aria-current", () => {
    renderRail();
    const home = screen.getByRole("link", { name: t(common.home) });
    expect(home.getAttribute("href")).toBe("#/home");
    expect(home.getAttribute("aria-current")).toBe("page");
    for (const name of [common.tenders, common.settings]) {
      const button = screen.getByRole("button", { name: t(name) });
      expect(button.hasAttribute("aria-current")).toBe(false);
      expect(hasTarget44(button)).toBe(true);
      expect(button.className).toMatch(/\bsize-12\b/);
      expect(button.className).toMatch(/hover:bg-accent/);
    }
    expect(home.className).toMatch(/aria-\[current=page\]:bg-background/);
  });

  it("is the first Tab stop and works from the keyboard", async () => {
    const { onSelect } = renderRail();
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole("link", { name: t(common.home) }));
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: t(common.tenders) }));
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("shows the item's name in a tooltip on the inline-end side", async () => {
    renderRail();
    await userEvent.tab();
    await userEvent.tab();
    const tip = await screen.findByText(t(common.tenders), { selector: '[data-slot="tooltip-content"], [data-slot="tooltip-content"] *' });
    expect(tip.closest("[data-side]")?.getAttribute("data-side")).toBe("inline-end");
  });
});
