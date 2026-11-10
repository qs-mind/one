import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Checkbox } from "@/design/ui/checkbox";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);

describe.each(DIRS)("Checkbox (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const name = text(controls.onDevice, lang);

  it("is reached by Tab, Space toggles aria-checked, 44px hit area", async () => {
    renderIn(dir, <Checkbox aria-label={name} />);
    const box = screen.getByRole("checkbox", { name });
    await userEvent.tab();
    expect(box).toHaveFocus();
    expect(box).toHaveAttribute("aria-checked", "false");
    await userEvent.keyboard(" ");
    expect(box).toHaveAttribute("aria-checked", "true");
    await userEvent.keyboard(" ");
    expect(box).toHaveAttribute("aria-checked", "false");
    expect(hasTarget44(box)).toBe(true);
  });

  it("draws with tokens: 20px, radius 4, Slate edge on card, primary when checked; no opacity", () => {
    renderIn(dir, <Checkbox aria-label={name} defaultChecked />);
    const list = classes(screen.getByRole("checkbox", { name }));
    expect(list).toEqual(
      expect.arrayContaining(["size-5", "rounded-sm", "border-muted-foreground", "bg-card", "data-checked:bg-primary"]),
    );
    expect(list.some((c) => c.includes("opacity-"))).toBe(false);
  });

  it("disabled and invalid are announced", async () => {
    renderIn(dir, <Checkbox aria-label={name} disabled aria-invalid />);
    const box = screen.getByRole("checkbox", { name });
    expect(box).toHaveAttribute("aria-disabled", "true");
    expect(box).toHaveAttribute("aria-invalid", "true");
    // Off reads as off: a filled grey box on a visible edge, not the near-invisible --border edge alone.
    expect(classes(box)).toEqual(expect.arrayContaining(["data-disabled:border-line", "data-disabled:bg-disabled"]));
    await userEvent.click(box);
    expect(box).toHaveAttribute("aria-checked", "false");
  });

  it("in a stack it sits in a 44px label that names it", async () => {
    renderIn(
      dir,
      <label className="flex min-h-11 items-center gap-3">
        <Checkbox />
        {name}
      </label>,
    );
    const box = screen.getByRole("checkbox", { name });
    expect(hasTarget44(box)).toBe(true);
    await userEvent.click(screen.getByText(name));
    expect(box).toHaveAttribute("aria-checked", "true");
  });
});
