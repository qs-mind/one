// The honest work log (ProgressLine with the core's data-worklog): while a Brief runs each step shows, a running one as
// a chip with its real elapsed time; when it ends, Thinking settles to the real time and step count, and the steps fold
// into that line and open again. Every time comes from the core's timestamps.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { duration, ProgressLine, tick } from "./ProgressLine";
import type { WorklogData, WorkStep } from "./types";

const lead = { en: "Lead QS", ar: "كبير مهندسي الكميات" };
const T0 = "2026-11-05T08:00:00.000Z";
const at = (seconds: number) => new Date(Date.parse(T0) + seconds * 1000).toISOString();
const step = (text: string, from: number, to: number | null): WorkStep => ({
  agent: lead,
  text: { en: text, ar: text },
  at: at(from),
  until: to === null ? null : at(to),
});

/** Six steps over 2 minutes 5 seconds, the last one ending as the Brief does. */
const finished: WorklogData = {
  started: T0,
  ended: at(125),
  steps: [
    step("بيقرا A-101.dwg", 1, 4),
    step("بيقرا المقايسة", 4, 10),
    step("بيسعّر البنود", 10, 60),
    step("بيراجع الأسعار", 60, 90),
    step("بيكتب الجدول", 90, 120),
    step("بيلخّص", 120, 125),
  ],
};

function motion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

beforeEach(() => {
  setLanguage("ar");
  motion(false);
});
afterEach(() => vi.useRealTimers());

describe("the settled line", () => {
  it("says the real time and step count from the core's timestamps", () => {
    render(<ProgressLine items={[]} worklog={finished} lang="ar" />);
    expect(screen.getByRole("button", { name: "اشتغل دقيقتين و5 ثواني · 6 خطوات" })).toBeInTheDocument();
  });

  it("in English too, and in whole words for any length", () => {
    setLanguage("en");
    render(<ProgressLine items={[]} worklog={finished} lang="en" />);
    expect(screen.getByRole("button", { name: "Worked for 2m 5s · 6 steps" })).toBeInTheDocument();
    expect(duration(42_400, "ar")).toBe("42 ثانية");
    expect(duration(1_000, "ar")).toBe("ثانية");
    expect(duration(12 * 60_000 + 7_000, "en")).toBe("12m"); // past ten minutes the seconds drop
    expect(duration(3_600_000 + 5 * 60_000, "ar")).toBe("ساعة و5 دقايق");
  });

  it("folds the steps into it, and opens them again", () => {
    render(<ProgressLine items={[]} worklog={finished} lang="ar" />);
    const line = screen.getByRole("button", { name: /اشتغل/ });
    expect(line).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("بيسعّر البنود")).toBeNull();
    fireEvent.click(line);
    expect(line).toHaveAttribute("aria-expanded", "true");
    const steps = within(screen.getByRole("list", { name: texts.workSteps.ar })).getAllByRole("listitem");
    expect(steps).toHaveLength(6);
    // each step with how long it really took: 50 s for the pricing
    expect(steps[2]).toHaveTextContent("بيسعّر البنود");
    expect(steps[2]).toHaveTextContent("50.0 ث");
    fireEvent.click(line);
    expect(screen.queryByText("بيسعّر البنود")).toBeNull();
  });
});

describe("while the Brief runs", () => {
  const running: WorklogData = { started: T0, ended: null, steps: [step("بيقرا المقايسة", 0, 3), step("بيقرا A-101.dwg", 3, null)] };

  it("Thinking shimmers and every step shows, none folded", () => {
    render(<ProgressLine items={[]} worklog={running} lang="ar" live />);
    expect(screen.getByText(texts.thinking.ar)).toHaveClass("shimmer");
    expect(screen.queryByRole("button", { name: /اشتغل/ })).toBeNull();
    expect(screen.getByText("بيقرا المقايسة")).toBeInTheDocument();
  });

  it("a running step is a chip whose timer counts the real time since the core said it began", () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse(at(3)) + 1200);
    render(<ProgressLine items={[]} worklog={running} lang="ar" live />);
    const chip = screen.getByText((_, el) => el?.hasAttribute("data-running") ?? false);
    expect(chip).toHaveTextContent("بيقرا A-101.dwg · 1.2 ث");
    act(() => vi.advanceTimersByTime(1000));
    expect(chip).toHaveTextContent("بيقرا A-101.dwg · 2.2 ث");
    act(() => vi.advanceTimersByTime(60_000));
    expect(chip).toHaveTextContent("1 د 02 ث");
    // three dots fade beside it while it really runs; a step done has none
    expect(chip.querySelector("[data-dots]")).not.toBeNull();
    expect(screen.getAllByText((_, el) => el?.hasAttribute("data-dots") ?? false)).toHaveLength(1);
  });

  it("settles when the core says it ended: the timer stops at the real end", () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse(at(3)) + 1200);
    const { rerender } = render(<ProgressLine items={[]} worklog={running} lang="ar" live />);
    const ended = { ...running, ended: at(9), steps: [running.steps[0]!, { ...running.steps[1]!, until: at(9) }] };
    rerender(<ProgressLine items={[]} worklog={ended} lang="ar" live={false} />);
    expect(screen.getByRole("button", { name: "اشتغل 9 ثواني · خطوتين" })).toBeInTheDocument();
    expect(screen.queryByText(texts.thinking.ar)).toBeNull();
    expect(document.querySelector("[data-running]")).toBeNull();
  });

  it("a step left open in a Brief that is not live has no timer: nothing ticks on its own", () => {
    render(<ProgressLine items={[]} worklog={running} lang="ar" />);
    expect(document.querySelector("[data-running]")).toBeNull();
    expect(screen.getByText("بيقرا A-101.dwg")).toBeInTheDocument();
  });

  it("with reduced motion: no shimmer, no fade and no ticking timer, just the text", () => {
    motion(true);
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse(at(3)) + 1200);
    render(<ProgressLine items={[]} worklog={running} lang="ar" live />);
    expect(screen.getByText(texts.thinking.ar)).not.toHaveClass("shimmer");
    expect(document.querySelector("[data-dots]")).toBeNull();
    const chip = screen.getByText((_, el) => el?.hasAttribute("data-running") ?? false);
    expect(chip).toHaveTextContent(/^بيقرا A-101.dwg$/);
  });
});

describe("the chip's time", () => {
  it("is tenths of a second under a minute, then minutes and seconds", () => {
    expect(tick(1234, "ar")).toBe("1.2 ث");
    expect(tick(1234, "en")).toBe("1.2 s");
    expect(tick(65_000, "en")).toBe("1m 05s");
  });
});
