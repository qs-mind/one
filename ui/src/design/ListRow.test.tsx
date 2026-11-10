import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ListRow } from "@/design/ListRow";
import { StatusDot } from "@/design/StatusDot";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const cls = (el: Element | null | undefined) => (el?.getAttribute("class") ?? "").split(/\s+/);
const hoverClasses = (el: Element) => cls(el).filter((c) => c.startsWith("hover:"));

describe.each(DIRS)("ListRow (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: { en: string; ar: string }, vars?: Record<string, number>) => text(pair, lang, vars);

  it.each([
    ["plain", ["-mx-3", "min-h-11", "gap-3", "rounded-lg", "px-3"]],
    ["divided", ["-mx-4", "flex-wrap", "gap-6", "rounded-xl", "py-5", "after:bg-border", "last:after:hidden"]],
    ["boxed", ["min-h-14", "gap-4", "rounded-xl", "border", "border-border", "px-5"]],
    ["panel", ["flex-wrap", "gap-4", "rounded-2xl", "bg-muted", "px-5", "py-4"]],
  ] as const)("frame %s has its classes", (frame, expected) => {
    const { container } = renderIn(dir, <ListRow frame={frame} title={t(surfaces.stageReading)} />);
    expect(cls(container.firstElementChild)).toEqual(expect.arrayContaining([...expected, "group/row", "text-start"]));
  });

  it("without render it is a passive div with no hover and no focus", () => {
    const { container } = renderIn(dir, <ListRow leading={<StatusDot state="done" />} title={t(surfaces.stageReading)} />);
    const row = container.firstElementChild!;
    expect(row.tagName).toBe("DIV");
    expect(hoverClasses(row)).toEqual([]);
    expect(row.hasAttribute("tabindex")).toBe(false);
    expect(cls(row)).not.toContain("focus-inset");
  });

  it("render makes it a link that keeps the caller's attributes, and only spans inside", () => {
    renderIn(
      dir,
      <ListRow frame="divided" size="lg" render={<a href="#/t/1" aria-current="page" />} title={t(surfaces.tenderOne)} meta={t(surfaces.tenderOneMeta)} trailing={t(surfaces.planDays, { n: 5 })} />,
    );
    const link = screen.getByRole("link", { name: `${t(surfaces.tenderOne)} ${t(surfaces.tenderOneMeta)} ${t(surfaces.planDays, { n: 5 })}` });
    expect(link.getAttribute("href")).toBe("#/t/1");
    expect(link.getAttribute("aria-current")).toBe("page");
    expect([...link.querySelectorAll("*")].every((el) => el.tagName === "SPAN")).toBe(true);
    expect(cls(link)).toEqual(expect.arrayContaining(["hover:bg-accent", "focus-inset"]));
    expect(screen.getByText(t(surfaces.tenderOne)).className).toMatch(/text-lg font-bold/);
  });

  it("a button row is found by 'title meta' (the space is in its name), reached by Tab, 44px", async () => {
    const onClick = vi.fn();
    renderIn(dir, <ListRow render={<button type="button" onClick={onClick} />} title={t(surfaces.contracts)} meta={t(surfaces.contractsMeta)} />);
    const button = screen.getByRole("button", { name: `${t(surfaces.contracts)} ${t(surfaces.contractsMeta)}` });
    expect(hasTarget44(button)).toBe(true);
    expect(cls(button)).toContain("py-2");
    await userEvent.tab();
    expect(document.activeElement).toBe(button);
    await userEvent.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("a filled row hovers with muted-hover, never accent, and its secondary text turns foreground (R2)", () => {
    renderIn(dir, <ListRow frame="panel" tone="strong" render={<button type="button" />} title={t(surfaces.approvePlan)} meta={t(surfaces.workPaused)} />);
    const row = screen.getByRole("button");
    expect(hoverClasses(row)).toEqual(["hover:bg-muted-hover"]);
    expect(cls(screen.getByText(t(surfaces.workPaused)))).toContain("group-hover/row:text-foreground");
    expect(screen.getByText(t(surfaces.approvePlan)).className).toMatch(/font-bold/);
  });

  it("current adds the Stone fill and the 700 title; boxed current loses its edge", () => {
    renderIn(dir, <ListRow frame="boxed" current render={<label />} title={t(surfaces.recommended)} meta={t(surfaces.recommendedMeta)} />);
    const row = screen.getByText(t(surfaces.recommended)).closest("label")!;
    expect(cls(row)).toEqual(expect.arrayContaining(["bg-muted", "text-foreground", "border-transparent", "hover:bg-muted-hover", "focus-ring-within"]));
    expect(cls(row)).not.toContain("hover:bg-accent");
    expect(cls(row)).not.toContain("focus-inset");
    expect(screen.getByText(t(surfaces.recommended)).className).toMatch(/font-bold/);
    expect(hasTarget44(row)).toBe(true);
  });

  it("tone muted greys the whole row; detail is foreground otherwise", () => {
    const { container, unmount } = renderIn(dir, <ListRow tone="muted" title={t(surfaces.stagePricing)} detail={t(surfaces.sourceBody)} />);
    expect(cls(container.firstElementChild)).toContain("text-muted-foreground");
    expect(cls(screen.getByText(t(surfaces.sourceBody)))).toContain("text-muted-foreground");
    unmount();
    renderIn(dir, <ListRow title={t(surfaces.stagePricing)} detail={t(surfaces.sourceBody)} />);
    expect(cls(screen.getByText(t(surfaces.sourceBody)))).toContain("text-foreground");
  });

  it("the trailing part is pushed to the end side by a logical margin", () => {
    renderIn(dir, <ListRow title={t(surfaces.stageReading)} trailing={t(surfaces.stateWaiting)} />);
    expect(cls(screen.getByText(t(surfaces.stateWaiting)))).toEqual(expect.arrayContaining(["ms-auto", "text-xs", "text-muted-foreground"]));
  });
});
