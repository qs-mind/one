import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Button, buttonVariants } from "@/design/ui/button";
import { controls } from "@/texts/design/controls";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);

describe.each(DIRS)("Button (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const label = text(controls.approve, lang);

  it("renders, is reached by Tab and has a 44px target", async () => {
    renderIn(dir, <Button>{label}</Button>);
    const button = screen.getByRole("button", { name: label });
    await userEvent.tab();
    expect(button).toHaveFocus();
    expect(hasTarget44(button)).toBe(true);
    expect(document.documentElement.dir).toBe(dir);
  });

  it("fires onClick with Enter and with Space", async () => {
    const onClick = vi.fn();
    renderIn(dir, <Button onClick={onClick}>{label}</Button>);
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it("loading: busy, disabled, no click, still focusable", async () => {
    const onClick = vi.fn();
    renderIn(dir, <Button loading onClick={onClick}>{text(controls.checking, lang)}</Button>);
    const button = screen.getByRole("button", { name: text(controls.checking, lang) });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("data-disabled");
    await userEvent.tab();
    expect(button).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("disabled is announced and not focusable", async () => {
    renderIn(dir, <Button disabled>{label}</Button>);
    const button = screen.getByRole("button", { name: label });
    expect(button).toBeDisabled();
    expect(classes(button)).toContain("data-disabled:bg-disabled");
    expect(classes(button).some((c) => c.includes("opacity-"))).toBe(false);
  });

  it.each([
    ["default", ["bg-primary", "text-primary-foreground", "hover:bg-primary-hover", "active:bg-primary-pressed"]],
    ["outline", ["border-line", "bg-transparent", "hover:bg-accent", "active:bg-pressed"]],
    ["ghost", ["bg-transparent", "hover:bg-accent", "active:bg-pressed"]],
    ["link", ["link", "text-foreground"]],
  ] as const)("variant %s renders its tokens", (variant, expected) => {
    renderIn(dir, <Button variant={variant}>{label}</Button>);
    const list = classes(screen.getByRole("button", { name: label }));
    for (const c of expected) expect(list).toContain(c);
  });

  it.each([
    ["default", ["h-11", "min-h-11", "rounded-lg", "px-5"]],
    ["lg", ["h-13", "min-h-13", "rounded-xl", "px-8"]],
    ["icon", ["size-11", "rounded-lg"]],
  ] as const)("size %s has its classes", (size, expected) => {
    renderIn(dir, <Button size={size} aria-label={label} />);
    const button = screen.getByRole("button", { name: label });
    for (const c of expected) expect(classes(button)).toContain(c);
    expect(hasTarget44(button)).toBe(true);
  });

  it("link has min-h-11 and no h-11", () => {
    renderIn(dir, <Button variant="link">{label}</Button>);
    const list = classes(screen.getByRole("button", { name: label }));
    expect(list).toContain("min-h-11");
    expect(list).not.toContain("h-11");
  });

  it("buttonVariants merges: a link on an <a> has no inline padding or radius of the base size", () => {
    const list = buttonVariants({ variant: "link", className: "text-xs" }).split(/\s+/);
    expect(list).toEqual(expect.arrayContaining(["px-0", "rounded-none", "text-xs"]));
    expect(list).not.toEqual(expect.arrayContaining(["px-5"]));
    expect(list).not.toContain("rounded-lg");
    expect(list).not.toContain("text-base");
  });

  it("wrap lets the label break: whitespace-normal, min-h-11, no h-11", () => {
    renderIn(dir, <Button wrap>{text(controls.longDecision, lang)}</Button>);
    const list = classes(screen.getByRole("button", { name: text(controls.longDecision, lang) }));
    expect(list).toContain("whitespace-normal");
    expect(list).toContain("min-h-11");
    expect(list).not.toContain("h-11");
  });
});
