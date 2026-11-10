// Shared plumbing for the design tests. Every test file: beforeEach(stubBrowser), afterEach(resetPage),
// and describe.each(DIRS) with renderIn(dir, …) so each case runs right to left and left to right.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { AppProviders } from "@/design/AppProviders";
import { setTheme } from "@/design/theme";
import { setLang } from "@/texts/language";
import type { Dir } from "@/texts/types";

export const DIRS: readonly Dir[] = ["rtl", "ltr"];

/** jsdom lacks matchMedia (sonner, the theme store) and getAnimations (Base UI's ScrollArea). Call in beforeEach:
 *  vi.stubGlobal at file top would be undone after the first test by the shared afterEach. */
export function stubBrowser(): void {
  if (typeof window.matchMedia !== "function") {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (query: string): MediaQueryList =>
        ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false,
        }) as MediaQueryList,
    });
  }
  Element.prototype.getAnimations ??= () => [];
}

/** Sets the page language for `dir` (so <html lang dir> are set, as in the app) and renders inside AppProviders. */
export function renderIn(dir: Dir, ui: ReactElement) {
  setLang(dir === "rtl" ? "ar" : "en");
  return render(<AppProviders>{ui}</AppProviders>);
}

/** Back to the start: Arabic, the system theme. */
export function resetPage(): void {
  setLang("ar");
  setTheme("system");
}

const TARGET_CLASSES = ["h-11", "min-h-11", "h-13", "min-h-13", "min-h-14", "size-11", "size-12", "after:-inset-3"];
const LABEL_CLASSES = ["min-h-11", "min-h-14"];

const classesOf = (el: Element): string[] => (el.getAttribute("class") ?? "").split(/\s+/);

/** jsdom has no layout: a 44px target is asserted by its class, or by a <label> around it that carries the height. */
export function hasTarget44(el: Element): boolean {
  if (classesOf(el).some((c) => TARGET_CLASSES.includes(c))) return true;
  const label = el.closest("label");
  return label !== null && classesOf(label).some((c) => LABEL_CLASSES.includes(c));
}
