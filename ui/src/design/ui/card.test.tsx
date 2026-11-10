import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Button } from "@/design/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/design/ui/card";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const classes = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);

describe.each(DIRS)("Card (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  function renderCard(props: Parameters<typeof Card>[0] = {}) {
    return renderIn(
      dir,
      <Card data-testid="card" {...props}>
        <CardHeader>
          <CardTitle>{text(surfaces.planTitle, lang)}</CardTitle>
          <CardDescription>{text(surfaces.planBody, lang)}</CardDescription>
          <CardAction>{text(surfaces.planDays, lang, { n: 12 })}</CardAction>
        </CardHeader>
        <CardContent>{text(surfaces.planBody, lang)}</CardContent>
        <CardFooter data-testid="footer">
          <Button variant="outline">{text(surfaces.discussPlan, lang)}</Button>
        </CardFooter>
      </Card>,
    );
  }

  it("renders the outline variant by default: Paper fill, a --line edge, radius 16, no ring", () => {
    renderCard();
    const card = screen.getByTestId("card");
    expect(card.getAttribute("data-variant")).toBe("outline");
    expect(classes(card)).toEqual(expect.arrayContaining(["border", "border-line", "bg-card", "rounded-2xl", "text-base"]));
    expect(card.className).not.toMatch(/\bring-|text-sm|shadow/);
  });

  it("renders the panel variant as a Stone block without an edge", () => {
    renderCard({ variant: "panel" });
    const card = screen.getByTestId("card");
    expect(card.getAttribute("data-variant")).toBe("panel");
    expect(classes(card)).toContain("bg-muted");
    expect(classes(card)).not.toContain("border-line");
  });

  it("sm sets the 8 gap, its padding, and the footer's extra 8", () => {
    renderCard({ size: "sm" });
    const card = screen.getByTestId("card");
    expect(card.getAttribute("data-size")).toBe("sm");
    expect(classes(card)).toEqual(
      expect.arrayContaining(["data-[size=sm]:[--card-gap:--spacing(2)]", "data-[size=sm]:[--card-px:--spacing(5)]"]),
    );
    expect(classes(screen.getByTestId("footer"))).toEqual(expect.arrayContaining(["group-data-[size=sm]/card:mt-2", "gap-3"]));
  });

  it("is passive: the card itself takes no focus, its button does", () => {
    renderCard();
    expect(screen.getByTestId("card").hasAttribute("tabindex")).toBe(false);
    expect(screen.getByRole("button", { name: text(surfaces.discussPlan, lang) })).toBeTruthy();
    expect(screen.getByText(text(surfaces.planTitle, lang)).className).toMatch(/font-bold/);
  });
});
