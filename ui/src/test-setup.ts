import "./polyfills";
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no layout. The viewers (Plan 6) size themselves from their container, so grid containers (role="grid")
// get a fixed size; React Flow (Plan 7) measures its pane and nodes, so an element with an inline width and height
// reports them. Every other element keeps jsdom's 0.
export const GRID_SIZE = { width: 1000, height: 600 };

if (typeof window !== "undefined") {
  const isGrid = (el: Element) => el.getAttribute("role") === "grid";
  const styled = (el: Element, side: "width" | "height") => parseFloat((el as HTMLElement).style?.[side] ?? "") || 0;
  const sizeOf = (el: Element) => ({
    width: styled(el, "width") || (isGrid(el) ? GRID_SIZE.width : 0),
    height: styled(el, "height") || (isGrid(el) ? GRID_SIZE.height : 0),
  });

  // Reports the element's size once, when it is observed (React Flow needs that to show its nodes).
  class ResizeObserverMock {
    constructor(private readonly callback: ResizeObserverCallback) {}
    observe(target: Element) {
      const { width, height } = sizeOf(target);
      const box = [{ inlineSize: width, blockSize: height }];
      const entry = {
        target,
        contentRect: new DOMRect(0, 0, width, height),
        borderBoxSize: box,
        contentBoxSize: box,
        devicePixelContentBoxSize: box,
      } as unknown as ResizeObserverEntry;
      this.callback([entry], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

  // React Flow reads the zoom from the viewport's transform: "translate(…) scale(n)".
  class DOMMatrixReadOnlyMock {
    m22: number;
    constructor(transform?: string) {
      const scale = /scale\(([-\d.e]+)\)/.exec(transform ?? "")?.[1];
      this.m22 = scale !== undefined ? Number(scale) : 1;
    }
  }
  window.DOMMatrixReadOnly ??= DOMMatrixReadOnlyMock as unknown as typeof DOMMatrixReadOnly;

  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return isGrid(this) ? GRID_SIZE.width : 0;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return isGrid(this) ? GRID_SIZE.height : 0;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return sizeOf(this).width;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return sizeOf(this).height;
    },
  });
  (SVGElement.prototype as unknown as { getBBox: () => DOMRect }).getBBox = () => new DOMRect(0, 0, 0, 0);
  Element.prototype.scrollIntoView ??= function scrollIntoView() {}; // cmdk keeps the chosen item in view
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  if (typeof document === "undefined") return; // a test that runs in Node, with no page
  localStorage.clear();
});
