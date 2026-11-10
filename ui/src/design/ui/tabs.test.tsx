import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/design/ui/tabs";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Tabs (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: { en: string; ar: string }) => text(pair, lang);

  function renderTabs() {
    return renderIn(
      dir,
      <Tabs defaultValue="sheet">
        <TabsList aria-label={t(surfaces.fileViews)}>
          <TabsTrigger value="sheet">{t(surfaces.tabSheet)}</TabsTrigger>
          <TabsTrigger value="text">{t(surfaces.tabText)}</TabsTrigger>
          <TabsTrigger value="history" disabled>
            {t(surfaces.tabHistory)}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="sheet">{t(surfaces.tabSheetBody)}</TabsContent>
        <TabsContent value="text">{t(surfaces.tabTextBody)}</TabsContent>
      </Tabs>,
    );
  }

  it("the list is the line variant by default and wraps; tabs are 44px, 17px, foreground; only disabled is muted", () => {
    renderTabs();
    expect(screen.getByRole("tablist").getAttribute("data-variant")).toBe("line");
    expect(screen.getByRole("tablist").className).toMatch(/(^|\s)max-w-full flex-wrap(\s|$)/);
    for (const tab of screen.getAllByRole("tab")) {
      expect(hasTarget44(tab)).toBe(true);
      expect(tab.className).toMatch(/\btext-base\b/);
      expect(tab.className).toMatch(/(^|\s)text-foreground(\s|$)/);
      expect(tab.className).toMatch(/(^|\s)data-disabled:text-muted-foreground(\s|$)/);
      expect(tab.className).toMatch(/(^|\s)hover:bg-accent(\s|$)/);
      expect(tab.className).not.toMatch(/font-medium|opacity-50|dark:|focus-visible:ring/);
    }
  });

  it("the current tab has aria-selected; the arrow toward the end moves forward", async () => {
    renderTabs();
    const [sheet, textTab] = screen.getAllByRole("tab");
    expect(sheet?.getAttribute("aria-selected")).toBe("true");
    await userEvent.tab();
    expect(document.activeElement).toBe(sheet);
    await userEvent.keyboard(dir === "rtl" ? "{ArrowLeft}" : "{ArrowRight}");
    expect(document.activeElement).toBe(textTab);
    await userEvent.keyboard("{Enter}");
    expect(textTab?.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText(t(surfaces.tabTextBody))).toBeTruthy();
  });

  it("a disabled tab is announced as disabled and is skipped", async () => {
    renderTabs();
    const history = screen.getByRole("tab", { name: t(surfaces.tabHistory) });
    expect(history.getAttribute("aria-disabled") ?? history.hasAttribute("disabled").toString()).toBe("true");
    await userEvent.click(history);
    expect(history.getAttribute("aria-selected")).toBe("false");
  });
});
