import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setZoom } from "../ui/scale";
import { useCompact, useNarrow, useSmall } from "./regions";

/** matchMedia for a window `width` px wide (CSS px, as the zoom leaves them). */
function windowWidth(width: number) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: width <= Number(/max-width: (\d+)px/.exec(query)?.[1] ?? Infinity),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}"))); // the zoom's save
}

const layout = () => ({ compact: useCompact(), narrow: useNarrow(), small: useSmall() });

describe("the layout's widths follow the engineer's zoom", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("at 100 % they are the window's own", () => {
    windowWidth(1280);
    expect(renderHook(layout).result.current).toEqual({ compact: false, narrow: false, small: false });
  });

  it("at 150 % a 1280 px window is laid out as 853 px is, and again at 100 % when the zoom goes back", () => {
    windowWidth(1280);
    const { result } = renderHook(layout);
    act(() => setZoom(1.5));
    expect(result.current).toEqual({ compact: true, narrow: true, small: false });
    act(() => setZoom(1));
    expect(result.current).toEqual({ compact: false, narrow: false, small: false });
  });

  it("at 80 % a 900 px window is laid out as 1125 px is: the chat stays beside the document", () => {
    windowWidth(900);
    const { result } = renderHook(layout);
    expect(result.current.narrow).toBe(true);
    act(() => setZoom(0.8));
    expect(result.current).toEqual({ compact: true, narrow: false, small: false });
  });
});
