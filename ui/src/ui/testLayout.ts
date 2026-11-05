// jsdom has no layout: the sliding marks' tests give elements their offsets (left, top, width, height) by a data key.
import { vi } from "vitest";

export type Box = { left: number; top: number; width: number; height: number };

/** Each element whose `data-k` (or `data-value`) is a key here reports that box; every other element reports 0. */
export function layout(boxes: Record<string, Box>) {
  const of = (el: HTMLElement) => boxes[el.dataset.k ?? el.dataset.value ?? ""];
  vi.spyOn(HTMLElement.prototype, "offsetLeft", "get").mockImplementation(function (this: HTMLElement) {
    return of(this)?.left ?? 0;
  });
  vi.spyOn(HTMLElement.prototype, "offsetTop", "get").mockImplementation(function (this: HTMLElement) {
    return of(this)?.top ?? 0;
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockImplementation(function (this: HTMLElement) {
    return of(this)?.width ?? 0;
  });
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(function (this: HTMLElement) {
    return of(this)?.height ?? 0;
  });
  // each element's offset parent is the one it sits in, so a mark adds the offsets up to its box
  vi.spyOn(HTMLElement.prototype, "offsetParent", "get").mockImplementation(function (this: HTMLElement) {
    return this.parentElement;
  });
}

/** The system's reduced-motion setting. */
export function motion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}
