import { act, render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScrollEdges } from "./useScrollEdges";

/** A scroll area with the given sizes (jsdom has no layout). */
function sized(el: HTMLElement, { height, content, top = 0 }: { height: number; content: number; top?: number }) {
  Object.defineProperty(el, "clientHeight", { configurable: true, get: () => height });
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => content });
  el.scrollTop = top;
}

function List({ children = <p>one line</p> }: { children?: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useScrollEdges(ref);
  return (
    <div ref={ref} data-testid="list" className="scroll-fade">
      {children}
    </div>
  );
}

const edges = (el: HTMLElement) => ({ top: el.hasAttribute("data-more-top"), bottom: el.hasAttribute("data-more-bottom") });

function scrollTo(el: HTMLElement, top: number) {
  el.scrollTop = top;
  act(() => void el.dispatchEvent(new Event("scroll")));
}

afterEach(() => vi.restoreAllMocks());

describe("useScrollEdges", () => {
  it("at the top with more below: only the bottom edge fades", () => {
    const { getByTestId } = render(<List />);
    const list = getByTestId("list");
    sized(list, { height: 300, content: 900 });
    scrollTo(list, 0);
    expect(edges(list)).toEqual({ top: false, bottom: true });
  });

  it("in the middle: both edges fade", () => {
    const { getByTestId } = render(<List />);
    const list = getByTestId("list");
    sized(list, { height: 300, content: 900 });
    scrollTo(list, 300);
    expect(edges(list)).toEqual({ top: true, bottom: true });
  });

  it("at the end: only the top edge fades", () => {
    const { getByTestId } = render(<List />);
    const list = getByTestId("list");
    sized(list, { height: 300, content: 900 });
    scrollTo(list, 600);
    expect(edges(list)).toEqual({ top: true, bottom: false });
  });

  it("when everything fits: no fade", () => {
    const { getByTestId } = render(<List />);
    const list = getByTestId("list");
    sized(list, { height: 300, content: 300 });
    scrollTo(list, 0);
    expect(edges(list)).toEqual({ top: false, bottom: false });
  });

  it("reads the sizes when it starts, before any scroll", () => {
    const content = { height: 300, content: 900 };
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => content.height);
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(() => content.content);
    const { getByTestId } = render(<List />);
    expect(edges(getByTestId("list"))).toEqual({ top: false, bottom: true });
  });

  it("RF5: an area as short as one line never fades, so the fade cannot hide its only line", () => {
    const { getByTestId } = render(<List />);
    const list = getByTestId("list");
    sized(list, { height: 40, content: 120 });
    scrollTo(list, 40);
    expect(edges(list)).toEqual({ top: false, bottom: false });
  });

  it("follows the content's size as it changes, without a scroll", () => {
    const observed: ResizeObserverCallback[] = [];
    class Watch {
      constructor(callback: ResizeObserverCallback) {
        observed.push(callback);
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", Watch);
    const { getByTestId } = render(<List />);
    const list = getByTestId("list");
    sized(list, { height: 300, content: 300 });
    act(() => observed.forEach((callback) => callback([], {} as ResizeObserver)));
    expect(edges(list).bottom).toBe(false);
    sized(list, { height: 300, content: 900 });
    act(() => observed.forEach((callback) => callback([], {} as ResizeObserver)));
    expect(edges(list).bottom).toBe(true);
  });

  it("removes its listener and observers when it unmounts", () => {
    const disconnect = vi.fn();
    class Watch {
      observe() {}
      unobserve() {}
      disconnect = disconnect;
    }
    vi.stubGlobal("ResizeObserver", Watch);
    const { getByTestId, unmount } = render(<List />);
    const list = getByTestId("list");
    const remove = vi.spyOn(list, "removeEventListener");
    unmount();
    expect(remove).toHaveBeenCalledWith("scroll", expect.any(Function));
    expect(disconnect).toHaveBeenCalled();
  });

  it("watches an area that appears after the first render (a list shown once it has loaded)", () => {
    function Later({ shown }: { shown: boolean }) {
      const ref = useRef<HTMLUListElement>(null);
      useScrollEdges(ref);
      return shown ? <ul ref={ref} data-testid="later" /> : <p>loading</p>;
    }
    const { rerender, getByTestId } = render(<Later shown={false} />);
    rerender(<Later shown />);
    const list = getByTestId("later");
    sized(list, { height: 300, content: 900 });
    scrollTo(list, 300);
    expect(edges(list)).toEqual({ top: true, bottom: true });
  });

  it("listens to scrolling passively", () => {
    const add = vi.spyOn(HTMLElement.prototype, "addEventListener");
    render(<List />);
    expect(add).toHaveBeenCalledWith("scroll", expect.any(Function), { passive: true });
  });
});
