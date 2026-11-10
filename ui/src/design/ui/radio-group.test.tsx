import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { RadioGroup, RadioGroupItem } from "@/design/ui/radio-group";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";
import type { Lang } from "@/texts/types";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);
const KEYS = ["recommended", "ownChoice", "onDevice"] as const;

/** A stack: each radio sits with its words in a 44px-high label, so the label is the target. */
function Stack({ lang, disabled }: { lang: Lang; disabled?: boolean }) {
  return (
    <RadioGroup aria-label={text(controls.models, lang)} defaultValue="recommended" disabled={disabled}>
      {KEYS.map((key) => (
        <label key={key} className="flex min-h-11 items-center gap-3">
          <RadioGroupItem value={key} />
          {text(controls[key], lang)}
        </label>
      ))}
    </RadioGroup>
  );
}

describe.each(DIRS)("RadioGroup (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const radio = (key: (typeof KEYS)[number]) => screen.getByRole("radio", { name: text(controls[key], lang) });

  it("each item sits in a min-h-11 label, 20px with a full hit area, and is reached by Tab", async () => {
    renderIn(dir, <Stack lang={lang} />);
    for (const key of KEYS) {
      const item = radio(key);
      expect(item.closest("label")?.getAttribute("class")).toMatch(/\bmin-h-11\b/);
      expect(hasTarget44(item)).toBe(true);
      expect(classes(item)).toEqual(expect.arrayContaining(["size-5", "after:-inset-3", "border-muted-foreground", "bg-card"]));
    }
    await userEvent.tab();
    expect(radio("recommended")).toHaveFocus();
    expect(radio("recommended")).toHaveAttribute("aria-checked", "true");
  });

  it(`moves forward with Arrow${dir === "rtl" ? "Left" : "Right"} and checks with Space`, async () => {
    renderIn(dir, <Stack lang={lang} />);
    await userEvent.tab();
    await userEvent.keyboard(dir === "rtl" ? "{ArrowLeft}" : "{ArrowRight}");
    expect(radio("ownChoice")).toHaveFocus();
    await userEvent.keyboard(" ");
    expect(radio("ownChoice")).toHaveAttribute("aria-checked", "true");
    expect(radio("recommended")).toHaveAttribute("aria-checked", "false");
  });

  it("checked fill is primary; disabled is announced without opacity", () => {
    renderIn(dir, <Stack lang={lang} disabled />);
    const item = radio("recommended");
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(classes(item)).toEqual(expect.arrayContaining(["data-checked:bg-primary", "data-disabled:border-line", "data-disabled:bg-disabled"]));
    expect(classes(item).some((c) => c.includes("opacity-"))).toBe(false);
    const dot = item.querySelector('[data-slot="radio-group-indicator"] span');
    expect(item).toHaveAttribute("data-disabled");
    expect(classes(dot!)).toContain("group-data-disabled/radio-group-item:bg-muted-foreground");
  });

  it("an invalid item is announced", () => {
    renderIn(
      dir,
      <RadioGroup aria-label={text(controls.models, lang)}>
        <label className="flex min-h-11 items-center gap-3">
          <RadioGroupItem value="x" aria-invalid aria-label={text(controls.ownChoice, lang)} />
        </label>
      </RadioGroup>,
    );
    expect(radio("ownChoice")).toHaveAttribute("aria-invalid", "true");
  });
});
