import { act, screen } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NOTIFY_MS, notify, notifyUndo } from "@/design/notify";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(() => {
  stubBrowser();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  act(() => toast.dismiss());
  vi.useRealTimers();
  resetPage();
});

const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));

describe.each(DIRS)("Toaster and notify (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: { en: string; ar: string }) => text(pair, lang);

  it("names the region exactly in the page language", () => {
    renderIn(dir, <p>x</p>);
    const region = screen.getByRole("region", { name: t(common.notifications) });
    expect(region.getAttribute("aria-label")).toBe(t(common.notifications));
  });

  it("notifyUndo stays until dismissed, with an undo and a close button named from texts", async () => {
    renderIn(dir, <p>x</p>);
    const onUndo = vi.fn();
    act(() => void notifyUndo(t(surfaces.fileRemoved), t(common.undo), onUndo));
    expect(await screen.findByText(t(surfaces.fileRemoved))).toBeTruthy();
    advance(60_000);
    expect(screen.getByText(t(surfaces.fileRemoved))).toBeTruthy();

    const toastEl = document.querySelector("[data-sonner-toast]");
    expect(toastEl?.getAttribute("data-styled")).not.toBe("true");
    expect(toastEl?.className).toMatch(/rounded-2xl/);
    expect(toastEl?.className).not.toMatch(/shadow/);

    const close = screen.getByRole("button", { name: t(common.close) });
    expect(hasTarget44(close)).toBe(true);
    const undo = screen.getByRole("button", { name: t(common.undo) });
    expect(hasTarget44(undo)).toBe(true);
    act(() => undo.click());
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it("notify is gone after 6s", async () => {
    renderIn(dir, <p>x</p>);
    act(() => void notify(t(surfaces.noteSaved)));
    expect(await screen.findByText(t(surfaces.noteSaved))).toBeTruthy();
    advance(NOTIFY_MS + 1000);
    expect(screen.queryByText(t(surfaces.noteSaved))).toBeNull();
  });
});
