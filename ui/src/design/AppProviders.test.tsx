import { act, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { setTheme, useTheme } from "@/design/theme";
import { useDirection } from "@/design/ui/direction";
import { Popover, PopoverContent, PopoverTrigger } from "@/design/ui/popover";
import { common } from "@/texts/common";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

function DirectionProbe() {
  return <span data-testid="probe">{useDirection()}</span>;
}

describe.each(DIRS)("AppProviders (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("puts lang and dir on <html>", () => {
    renderIn(dir, <p>x</p>);
    expect(document.documentElement.lang).toBe(lang);
    expect(document.documentElement.dir).toBe(dir);
  });

  it("gives a portalled popup the page's direction and logical sides", async () => {
    const { container } = renderIn(
      dir,
      <Popover>
        <PopoverTrigger>{text(common.settings, lang)}</PopoverTrigger>
        <PopoverContent side="inline-end">
          <DirectionProbe />
        </PopoverContent>
      </Popover>,
    );
    await userEvent.click(screen.getByRole("button", { name: text(common.settings, lang) }));
    const probe = await screen.findByTestId("probe");
    expect(probe.textContent).toBe(dir);
    expect(probe.closest("[data-side]")?.getAttribute("data-side")).toBe("inline-end");
    expect(container.contains(probe)).toBe(false); // portalled under <body>, outside any wrapper
  });

  it("names the notices region in the page language, and nothing else", () => {
    renderIn(dir, <p>x</p>);
    const region = screen.getByRole("region", { name: text(common.notifications, lang) });
    expect(region.getAttribute("aria-label")).toBe(text(common.notifications, lang));
  });
});

describe("theme store", () => {
  beforeEach(stubBrowser);

  it("sets and removes data-theme on <html> and resolves the theme", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.setting).toBe("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(result.current.resolved).toBe("light"); // the stub reports a light system

    act(() => setTheme("dark"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(result.current).toMatchObject({ setting: "dark", resolved: "dark" });

    act(() => result.current.setTheme("light"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(result.current.resolved).toBe("light");

    act(() => setTheme("system"));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(result.current.setting).toBe("system");
  });
});
