import "./polyfills";
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no layout. The viewers (Plan 6) size themselves from their container, so give them a
// ResizeObserver that never fires and a fixed size for grid containers (role="grid"); every other
// element keeps jsdom's 0.
export const GRID_SIZE = { width: 1000, height: 600 };

if (typeof window !== "undefined") {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
  const sized = (el: Element, size: number) => (el.getAttribute("role") === "grid" ? size : 0);
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return sized(this, GRID_SIZE.width);
    },
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return sized(this, GRID_SIZE.height);
    },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  if (typeof document === "undefined") return; // a test that runs in Node, with no page
  localStorage.clear();
});
