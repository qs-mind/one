import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SectionLabel } from "@/design/SectionLabel";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("SectionLabel (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("SectionLabel is an h2 by default, 15px 400 muted", () => {
    renderIn(dir, <SectionLabel>{text(surfaces.stages, lang)}</SectionLabel>);
    const heading = screen.getByRole("heading", { level: 2, name: text(surfaces.stages, lang) });
    expect(heading.className).toMatch(/\btext-xs\b/);
    expect(heading.className).toMatch(/\bfont-normal\b/);
    expect(heading.className).toMatch(/\btext-muted-foreground\b/);
  });

  it.each(["h3", "div"] as const)("SectionLabel renders as %s", (tag) => {
    renderIn(dir, <SectionLabel as={tag}>{text(surfaces.teamNow, lang)}</SectionLabel>);
    expect(screen.getByText(text(surfaces.teamNow, lang)).tagName).toBe(tag.toUpperCase());
  });
});
