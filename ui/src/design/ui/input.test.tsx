import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Input } from "@/design/ui/input";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);

describe.each(DIRS)("Input (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const name = text(controls.firstName, lang);

  it("follows the page: no dir by default; is reached by Tab; types; 52px", async () => {
    renderIn(dir, <Input aria-label={name} />);
    const input = screen.getByRole("textbox", { name });
    expect(input).not.toHaveAttribute("dir");
    await userEvent.tab();
    expect(input).toHaveFocus();
    await userEvent.keyboard("ONE 12");
    expect(input).toHaveValue("ONE 12");
    expect(hasTarget44(input)).toBe(true);
    expect(classes(input)).toEqual(expect.arrayContaining(["h-13", "rounded-xl", "border-input", "bg-card", "px-4"]));
  });

  it("passes dir=ltr through for keys, paths and numbers", () => {
    renderIn(dir, <Input aria-label={name} dir="ltr" inputMode="decimal" />);
    expect(screen.getByRole("textbox", { name })).toHaveAttribute("dir", "ltr");
  });

  it("bare has no edge and no fill", () => {
    renderIn(dir, <Input aria-label={name} variant="bare" />);
    const list = classes(screen.getByRole("textbox", { name }));
    expect(list).toContain("border-0");
    expect(list).toContain("h-11");
    expect(list.some((c) => /^border-(input|line|border)$/.test(c))).toBe(false);
  });

  it("error is announced through aria-invalid and draws a 2px foreground edge", () => {
    renderIn(dir, <Input aria-label={name} aria-invalid />);
    const input = screen.getByRole("textbox", { name });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(classes(input)).toEqual(expect.arrayContaining(["aria-invalid:border-2", "aria-invalid:border-foreground"]));
  });

  it("disabled is announced and drawn without opacity", () => {
    renderIn(dir, <Input aria-label={name} disabled />);
    const input = screen.getByRole("textbox", { name });
    expect(input).toBeDisabled();
    expect(classes(input)).toContain("data-disabled:text-muted-foreground");
    expect(classes(input).some((c) => c.includes("opacity-"))).toBe(false);
  });
});
