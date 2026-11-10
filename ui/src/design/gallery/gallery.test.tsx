// The gallery page: every demo of section 7.1, the four specimens, the switches and the address.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { foundation } from "@/texts/design/foundation";
import { specimens } from "@/texts/design/specimens";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";
import { parseHash, toHash } from "./address";
import { Gallery } from "./Gallery";
import { STAGES } from "./specimens/TenderSide";

beforeEach(stubBrowser);
afterEach(() => {
  window.location.hash = "";
  resetPage();
});

const DEMOS = {
  foundation: ["colours", "type", "space", "radius", "icons", "density", "now-waiting", "meta-num", "wordmark"],
  controls: ["button", "hold-button", "input", "textarea", "select", "radio-group", "checkbox", "label", "field", "tooltip", "pill"],
  surfaces: ["card", "dialog", "popover", "tabs", "progress", "stage-bar", "skeleton", "collapsible", "rail", "separator", "scroll-area", "toasts", "list-row", "section-label", "status-dot"],
};
const SPECIMENS = ["tender-side", "conversation", "message-box", "mixed"];

const ids = (container: HTMLElement, attribute: string) =>
  [...container.querySelectorAll(`[${attribute}]`)].map((el) => el.getAttribute(attribute));

describe("address", () => {
  it("reads every part and falls back to the gallery, Arabic, the system theme", () => {
    expect(parseHash("#/specimens/en/dark")).toEqual({ view: "specimens", lang: "en", theme: "dark" });
    expect(parseHash("#/gallery")).toEqual({ view: "gallery", lang: "ar", theme: "system" });
    expect(parseHash("")).toEqual({ view: "gallery", lang: "ar", theme: "system" });
    expect(parseHash("#/nope/fr/blue")).toEqual({ view: "gallery", lang: "ar", theme: "system" });
    expect(toHash({ view: "specimens", lang: "ar", theme: "light" })).toBe("#/specimens/ar/light");
  });
});

describe.each(DIRS)("Gallery (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("shows every demo id of the specification, in order", () => {
    window.location.hash = `#/gallery/${lang}/system`;
    const { container } = renderIn(dir, <Gallery />);
    expect(ids(container, "data-demo")).toEqual([...DEMOS.foundation, ...DEMOS.controls, ...DEMOS.surfaces]);
  });

  it("renders the four specimens, each under its sample label", () => {
    window.location.hash = `#/specimens/${lang}/system`;
    const { container } = renderIn(dir, <Gallery />);
    expect(ids(container, "data-specimen")).toEqual(SPECIMENS);
    for (const section of container.querySelectorAll("[data-specimen]"))
      expect(within(section as HTMLElement).getAllByText(text(common.sample, lang)).length).toBeGreaterThan(0);
  });

  it("reads the address at start", () => {
    window.location.hash = `#/specimens/${lang}/dark`;
    renderIn(dir, <Gallery />);
    expect(document.documentElement).toHaveAttribute("lang", lang);
    expect(document.documentElement).toHaveAttribute("dir", dir);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(screen.getByRole("heading", { name: text(specimens.tenderSide, lang) })).toBeTruthy();
  });

  it("the language switch flips <html lang dir> and writes the address", async () => {
    window.location.hash = `#/gallery/${lang}/system`;
    renderIn(dir, <Gallery />);
    const other = lang === "ar" ? "en" : "ar";
    const group = screen.getByRole("group", { name: text(foundation.language, lang) });
    await userEvent.click(within(group).getByRole("button", { name: text(foundation[other === "ar" ? "arabic" : "english"], other) }));
    await waitFor(() => expect(document.documentElement).toHaveAttribute("lang", other));
    expect(document.documentElement).toHaveAttribute("dir", other === "ar" ? "rtl" : "ltr");
    expect(window.location.hash).toBe(`#/gallery/${other}/system`);
  });

  it("the theme switch sets data-theme, and the pressed button says which", async () => {
    window.location.hash = `#/gallery/${lang}/system`;
    renderIn(dir, <Gallery />);
    const group = screen.getByRole("group", { name: text(foundation.theme, lang) });
    const dark = within(group).getByRole("button", { name: text(foundation.themeDark, lang) });
    expect(dark).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(dark);
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
    expect(dark).toHaveAttribute("aria-pressed", "true");
  });

  it("the stage rows of specimen 1 are not focusable", () => {
    window.location.hash = `#/specimens/${lang}/system`;
    renderIn(dir, <Gallery />);
    const aside = screen.getByRole("complementary", { name: text(specimens.tenderStatus, lang) });
    for (const stage of STAGES) {
      const row = within(aside).getByText(text(stage, lang)).closest(".group\\/row");
      expect(row?.tagName).toBe("DIV");
      expect(row).not.toHaveAttribute("tabindex");
    }
    // The waiting item and the team rows are buttons.
    expect(within(aside).getByRole("button", { name: new RegExp(text(surfaces.approvePlan, lang)) })).toBeTruthy();
  });
});
