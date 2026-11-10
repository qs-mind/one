import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";
import { SurfacesSection } from "./SurfacesSection";

beforeEach(stubBrowser);
afterEach(resetPage);

const IDS = ["card", "dialog", "popover", "tabs", "progress", "stage-bar", "skeleton", "collapsible", "rail", "separator", "scroll-area", "toasts", "list-row", "section-label", "status-dot"];

describe.each(DIRS)("SurfacesSection (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("shows every surfaces demo, each named", () => {
    const { container } = renderIn(dir, <SurfacesSection />);
    expect([...container.querySelectorAll("[data-demo]")].map((el) => el.getAttribute("data-demo"))).toEqual(IDS);
    for (const id of IDS) expect(screen.getByRole("region", { name: new RegExp(id.replace("-", ""), "i") })).toBeTruthy();
  });

  it("opens a notice with undo from the toasts demo", async () => {
    renderIn(dir, <SurfacesSection />);
    await userEvent.click(screen.getByRole("button", { name: text(surfaces.showUndo, lang) }));
    expect(await screen.findByText(text(surfaces.fileRemoved, lang))).toBeTruthy();
  });
});
