// Undo instead of "are you sure?": what was removed is gone at once, and «اتشال · تراجع» shows in its place with a thin
// line shrinking over the core's real window. Pointing at it or focusing Undo pauses the line, and the core's window.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { UndoNotice } from "./UndoNotice";

const UNDO_GONE = { en: "Too late to undo.", ar: "وقت التراجع خلص." };

function core(undo: () => Response = () => new Response(null, { status: 204 })) {
  const fetch = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/undo/tok") return undo();
    return new Response(null, { status: 204 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const posted = (fetch: ReturnType<typeof core>) => fetch.mock.calls.map(([url]) => String(url));

function motion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
  const animation = { pause: vi.fn(), play: vi.fn(), cancel: vi.fn() };
  const animate = vi.fn(() => animation as unknown as Animation);
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
  return { animate, animation };
}

function setup() {
  const onUndone = vi.fn();
  const onEnd = vi.fn();
  render(<UndoNotice label="اتشال «عينة»" token="tok" windowMs={6000} onUndone={onUndone} onEnd={onEnd} />);
  return { onUndone, onEnd, undo: screen.getByRole("button", { name: texts.undo.ar }) };
}

beforeEach(() => {
  setLanguage("ar");
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("UndoNotice", () => {
  it("says what was removed, with Undo, and a line shrinking over the real window", () => {
    const { animate } = motion(false);
    core();
    setup();
    expect(screen.getByRole("status")).toHaveTextContent("اتشال «عينة» · تراجع");
    expect(animate).toHaveBeenCalledWith([{ transform: "scaleX(1)" }, { transform: "scaleX(0)" }], expect.objectContaining({ duration: 6000, easing: "linear" }));
  });

  it("Undo inside the window takes it back", async () => {
    motion(false);
    const fetch = core();
    const { onUndone, onEnd, undo } = setup();
    act(() => vi.advanceTimersByTime(5000));
    await act(async () => fireEvent.click(undo));
    expect(posted(fetch)).toContain("/api/undo/tok");
    expect(onUndone).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(5000));
    expect(onEnd).not.toHaveBeenCalled();
  });

  it("after the window it is gone for good: no Undo is sent", () => {
    motion(false);
    const fetch = core();
    const { onEnd } = setup();
    act(() => vi.advanceTimersByTime(5999));
    expect(onEnd).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(posted(fetch)).not.toContain("/api/undo/tok");
  });

  it("pointing at it pauses the line and the core's window, for as long as it takes", () => {
    const { animation } = motion(false);
    const fetch = core();
    const { onEnd } = setup();
    act(() => vi.advanceTimersByTime(4000));
    fireEvent.pointerEnter(screen.getByRole("status"));
    expect(animation.pause).toHaveBeenCalled();
    expect(posted(fetch)).toContain("/api/undo/tok/pause");
    act(() => vi.advanceTimersByTime(60_000));
    expect(onEnd).not.toHaveBeenCalled();
    fireEvent.pointerLeave(screen.getByRole("status"));
    expect(animation.play).toHaveBeenCalled();
    expect(posted(fetch)).toContain("/api/undo/tok/resume");
    act(() => vi.advanceTimersByTime(1999));
    expect(onEnd).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onEnd).toHaveBeenCalledTimes(1); // the 2 s it had left
  });

  it("focusing Undo pauses it too", () => {
    motion(false);
    core();
    const { onEnd, undo } = setup();
    fireEvent.focus(undo);
    act(() => vi.advanceTimersByTime(30_000));
    expect(onEnd).not.toHaveBeenCalled();
    fireEvent.blur(undo);
    act(() => vi.advanceTimersByTime(6000));
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it("too late at the core: says so in the core's words", async () => {
    motion(false);
    core(() => Response.json({ error: UNDO_GONE }, { status: 404 }));
    const { onUndone, undo } = setup();
    await act(async () => fireEvent.click(undo));
    expect(onUndone).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(UNDO_GONE.ar);
  });

  it("with reduced motion: no line moves, and the window is just as long", () => {
    const { animate } = motion(true);
    core();
    const { onEnd } = setup();
    expect(animate).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(6000));
    expect(onEnd).toHaveBeenCalledTimes(1);
  });
});
