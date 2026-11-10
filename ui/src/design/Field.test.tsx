import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AppProviders } from "@/design/AppProviders";
import { Field } from "@/design/Field";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Input } from "@/design/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";
import type { Lang } from "@/texts/types";

beforeEach(stubBrowser);
afterEach(resetPage);

const describedBy = (el: Element) =>
  (el.getAttribute("aria-describedby") ?? "")
    .split(/\s+/)
    .map((id) => document.getElementById(id)?.textContent ?? "")
    .join(" | ");

function KeyField({ lang, error }: { lang: Lang; error?: boolean }) {
  return (
    <Field
      label={text(controls.apiKey, lang)}
      help={text(controls.keyChecking, lang)}
      error={error ? text(controls.keyRejected, lang) : undefined}
    >
      <Input dir="ltr" />
    </Field>
  );
}

describe.each(DIRS)("Field (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const name = text(controls.apiKey, lang);

  it("the label names the control; help is in aria-describedby; no error node without an error", async () => {
    renderIn(dir, <KeyField lang={lang} />);
    const input = screen.getByRole("textbox", { name });
    expect(describedBy(input)).toContain(text(controls.keyChecking, lang));
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText(text(controls.keyRejected, lang))).toBeNull();
    await userEvent.tab();
    expect(input).toHaveFocus();
  });

  it("an error sets aria-invalid and is described, inside a polite region that was there before", () => {
    const { rerender } = renderIn(dir, <KeyField lang={lang} />);
    const region = document.querySelector('[aria-live="polite"]');
    expect(region).not.toBeNull();
    act(() =>
      rerender(
        <AppProviders>
          <KeyField lang={lang} error />
        </AppProviders>,
      ),
    );
    const input = screen.getByRole("textbox", { name });
    const message = screen.getByText(text(controls.keyRejected, lang));
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(describedBy(input)).toContain(text(controls.keyRejected, lang));
    expect(describedBy(input)).toContain(text(controls.keyChecking, lang));
    expect(message.closest('[aria-live="polite"]')).toBe(region);
    expect(message.getAttribute("class")).toMatch(/\bfont-bold\b/);
    expect(message.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("works around the unit box", () => {
    renderIn(
      dir,
      <Field label={text(controls.monthlyCap, lang)} error={text(controls.keyRejected, lang)}>
        <div className="focus-ring-within flex h-13 items-center gap-2 rounded-xl border border-input bg-card px-4">
          <Input variant="bare" dir="ltr" inputMode="decimal" />
          <span className="shrink-0 text-xs text-muted-foreground">{text(controls.currency, lang)}</span>
        </div>
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: text(controls.monthlyCap, lang) });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(describedBy(input)).toContain(text(controls.keyRejected, lang));
  });

  it("works around Select", () => {
    const items = [{ value: "owner", label: text(controls.owner, lang) }];
    renderIn(
      dir,
      <Field label={text(controls.orgType, lang)} help={text(controls.roleExample, lang)}>
        <Select items={items} defaultValue="owner">
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="owner">{items[0]?.label}</SelectItem>
          </SelectContent>
        </Select>
      </Field>,
    );
    const trigger = screen.getByRole("combobox", { name: text(controls.orgType, lang) });
    expect(describedBy(trigger)).toContain(text(controls.roleExample, lang));
  });

  it("lg label is the 19px heading", () => {
    renderIn(
      dir,
      <Field label={text(controls.models, lang)} labelSize="lg">
        <Input />
      </Field>,
    );
    expect(screen.getByText(text(controls.models, lang)).getAttribute("class")).toMatch(/\btext-lg\b/);
  });
});
