import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Input } from "@/design/ui/input";
import { Label } from "@/design/ui/label";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);

describe.each(DIRS)("Label (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const name = text(controls.firstName, lang);

  it("names its control and is not focusable itself", () => {
    renderIn(
      dir,
      <>
        <Label htmlFor="first">{name}</Label>
        <Input id="first" />
      </>,
    );
    expect(screen.getByRole("textbox", { name })).toBeInTheDocument();
    expect(screen.getByText(name)).not.toHaveAttribute("tabindex");
  });

  it("default is the 15px Slate form label; lg the 19px 700 heading; no leading-none or opacity", () => {
    renderIn(
      dir,
      <>
        <Label>{name}</Label>
        <Label size="lg">{text(controls.models, lang)}</Label>
      </>,
    );
    const small = classes(screen.getByText(name));
    const large = classes(screen.getByText(text(controls.models, lang)));
    expect(small).toEqual(expect.arrayContaining(["text-xs", "text-muted-foreground"]));
    expect(large).toEqual(expect.arrayContaining(["text-lg", "font-bold", "text-foreground"]));
    for (const list of [small, large]) {
      expect(list).not.toContain("leading-none");
      expect(list).not.toContain("font-medium");
      expect(list.some((c) => c.includes("opacity-"))).toBe(false);
    }
  });
});
