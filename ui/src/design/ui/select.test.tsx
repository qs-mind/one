import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";
import type { Lang } from "@/texts/types";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);

function OrgSelect({ lang, disabled, invalid }: { lang: Lang; disabled?: boolean; invalid?: boolean }) {
  const items = (["contractor", "consultant", "owner", "supplier"] as const).map((value) => ({
    value,
    label: text(controls[value], lang),
  }));
  return (
    <Select items={items} defaultValue="contractor" disabled={disabled}>
      <SelectTrigger aria-label={text(controls.orgType, lang)} aria-invalid={invalid || undefined}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

describe.each(DIRS)("Select (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const name = text(controls.orgType, lang);

  it("shows the label, is reached by Tab, 52px like a field", async () => {
    renderIn(dir, <OrgSelect lang={lang} />);
    const trigger = screen.getByRole("combobox", { name });
    expect(trigger).toHaveTextContent(text(controls.contractor, lang));
    expect(trigger).not.toHaveTextContent("contractor");
    await userEvent.tab();
    expect(trigger).toHaveFocus();
    expect(hasTarget44(trigger)).toBe(true);
    expect(classes(trigger)).toEqual(expect.arrayContaining(["h-13", "rounded-xl", "bg-card", "w-full"]));
  });

  it("opens with Enter, ArrowDown + Enter picks, Escape closes", async () => {
    renderIn(dir, <OrgSelect lang={lang} />);
    const trigger = screen.getByRole("combobox", { name });
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    const list = await screen.findByRole("listbox");
    const options = screen.getAllByRole("option");
    for (const option of options) {
      expect(classes(option)).toContain("focus-inset");
      expect(hasTarget44(option)).toBe(true);
    }
    // The list sits in a portal: its direction comes from <html>, set by the language store.
    expect(list.closest("[dir]")?.getAttribute("dir")).toBe(dir);
    expect(getComputedStyle(list).direction).toBe(dir);
    await waitFor(() => expect(options[0]).toHaveFocus());
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await waitFor(() => expect(trigger).toHaveTextContent(text(controls.consultant, lang)));
    // Base UI closes the list and hands focus back to the trigger a moment after the pick: reopen only then.
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
    await userEvent.keyboard("{Enter}");
    await screen.findByRole("listbox");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    expect(trigger).toHaveTextContent(text(controls.consultant, lang));
  });

  it("disabled and error are announced", () => {
    renderIn(dir, <OrgSelect lang={lang} disabled invalid />);
    const trigger = screen.getByRole("combobox", { name });
    expect(trigger).toHaveAttribute("data-disabled");
    expect(trigger).toHaveAttribute("aria-invalid", "true");
    expect(classes(trigger).some((c) => c.includes("opacity-"))).toBe(false);
  });
});
