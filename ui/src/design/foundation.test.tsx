// The foundation pieces: MetaLine, Num, Wordmark, the theme store, and the direction AppProviders gives a portal.
import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MetaLine } from "@/design/MetaLine";
import { Num } from "@/design/Num";
import { setTheme } from "@/design/theme";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Popover, PopoverContent, PopoverTrigger } from "@/design/ui/popover";
import { Wordmark } from "@/design/Wordmark";
import { common } from "@/texts/common";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("foundation (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("MetaLine isolates each item, hides the dots, and keeps a space on each side of them", () => {
    const { container } = renderIn(dir, <MetaLine items={["Lead QS", "", null, "14 ملف"]} />);
    const parts = [...container.querySelectorAll("bdi")].map((el) => el.textContent);
    expect(parts).toEqual(["Lead QS", "14 ملف"]);
    const dots = container.querySelectorAll('[aria-hidden="true"]');
    expect(dots).toHaveLength(1);
    expect(dots[0]?.textContent).toBe("·");
    expect(container.textContent).toBe("Lead QS · 14 ملف");
  });

  it("Num is left to right, isolated, with Western digits", () => {
    const { container } = renderIn(dir, <Num value={-1800} />);
    const num = container.querySelector("bdi");
    expect(num).toHaveAttribute("dir", "ltr");
    expect(num).toHaveClass("num");
    expect(num?.textContent).toMatch(/1,800/);
    expect(num?.textContent).not.toMatch(/[٠-٩۰-۹]/);
  });

  it("Num shows a ready string as given", () => {
    renderIn(dir, <Num>7/03</Num>);
    expect(screen.getByText("7/03")).toHaveAttribute("dir", "ltr");
  });

  it("Wordmark reads ONE, in Latin, never translated", () => {
    renderIn(dir, <Wordmark />);
    const mark = screen.getByText("ONE");
    expect(mark).toHaveAttribute("lang", "en");
    expect(mark).toHaveAttribute("dir", "ltr");
  });

  it("setTheme sets and removes data-theme", () => {
    renderIn(dir, <span />);
    setTheme("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    setTheme("light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    setTheme("system");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("AppProviders gives a portalled popup the page's direction", async () => {
    renderIn(
      dir,
      <Popover defaultOpen>
        <PopoverTrigger>{text(common.settings, lang)}</PopoverTrigger>
        <PopoverContent>{text(common.close, lang)}</PopoverContent>
      </Popover>,
    );
    const popup = await screen.findByText(text(common.close, lang));
    expect(document.documentElement).toHaveAttribute("dir", dir);
    expect(getComputedStyle(popup).direction).toBe(dir);
  });
});
