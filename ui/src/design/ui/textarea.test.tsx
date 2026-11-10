import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Textarea } from "@/design/ui/textarea";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);

describe.each(DIRS)("Textarea (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const name = text(controls.notes, lang);

  it("follows the page, is reached by Tab, and keeps one element while lines are typed", async () => {
    renderIn(dir, <Textarea aria-label={name} />);
    const box = screen.getByRole("textbox", { name });
    expect(box).not.toHaveAttribute("dir");
    await userEvent.tab();
    expect(box).toHaveFocus();
    await userEvent.keyboard("one{Shift>}{Enter}{/Shift}two{Shift>}{Enter}{/Shift}three");
    expect(screen.getByRole("textbox", { name })).toBe(box);
    expect((box as HTMLTextAreaElement).value.split("\n")).toHaveLength(3);
    expect(hasTarget44(box)).toBe(true);
    expect(classes(box)).toEqual(expect.arrayContaining(["min-h-13", "rounded-xl", "max-h-45", "field-sizing-content"]));
  });

  it("grows by script where field-sizing is missing, up to 180px", async () => {
    vi.spyOn(CSS, "supports").mockReturnValue(false);
    renderIn(dir, <Textarea aria-label={name} />);
    const box = screen.getByRole("textbox", { name });
    expect(box).toHaveAttribute("rows", "1");
    Object.defineProperty(box, "scrollHeight", { configurable: true, value: 400 });
    await userEvent.type(box, "x");
    expect(box.style.height).toBe("180px");
    vi.restoreAllMocks();
  });

  it("leaves sizing to CSS where field-sizing exists", () => {
    vi.spyOn(CSS, "supports").mockReturnValue(true);
    renderIn(dir, <Textarea aria-label={name} />);
    expect(screen.getByRole("textbox", { name })).not.toHaveAttribute("rows");
    vi.restoreAllMocks();
  });

  it("passes dir=ltr through; bare has min-h-11 and no edge", () => {
    renderIn(dir, <Textarea aria-label={name} dir="ltr" variant="bare" />);
    const box = screen.getByRole("textbox", { name });
    expect(box).toHaveAttribute("dir", "ltr");
    expect(classes(box)).toEqual(expect.arrayContaining(["min-h-11", "border-0", "bg-transparent"]));
    expect(classes(box)).not.toContain("border-input");
  });

  it("error and disabled are announced", () => {
    renderIn(dir, <Textarea aria-label={name} aria-invalid disabled />);
    const box = screen.getByRole("textbox", { name });
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(box).toBeDisabled();
    expect(classes(box).some((c) => c.includes("opacity-"))).toBe(false);
  });
});
