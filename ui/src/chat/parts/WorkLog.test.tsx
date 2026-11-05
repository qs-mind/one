// The honest work log (ProgressLine with the core's data-worklog): while a Brief runs each step shows, a running one as
// a chip with its real elapsed time; when it ends, Thinking settles to the real time and step count, and the steps fold
// into that line and open again. Every time comes from the core's timestamps.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { count, setLanguage, texts } from "../../i18n";
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

describe("who did each step", () => {
  const checker = { en: "Checking QS", ar: "مهندس المراجعة" };
  const log: WorklogData = {
    started: T0,
    ended: at(20),
    steps: [
      step("بيشوف ملفات المشروع", 0, 2),
      step("بيقرا المواصفات", 2, 4),
      step("بيستورد المقايسة", 4, 6),
      step("بيستورد المقايسة", 6, 9),
      { ...step("بيراجع الأسعار", 9, 15), agent: checker },
      step("بيلخّص", 15, 20),
    ],
  };

  it("names the agent once per run of its steps, and folds the same result line repeated into one", () => {
    render(<ProgressLine items={[]} worklog={log} lang="ar" />);
    fireEvent.click(screen.getByRole("button", { name: /اشتغل/ }));
    const list = screen.getByRole("list", { name: texts.workSteps.ar });
    // three runs: the Lead QS, the Checking QS, the Lead QS again
    expect([...list.querySelectorAll("[data-agent]")].map((el) => el.textContent)).toEqual([lead.ar, checker.ar, lead.ar]);
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(5);
    expect(within(list).getAllByText("بيستورد المقايسة")).toHaveLength(1);
    expect(rows[2]).toHaveTextContent("×2");
    expect(rows[2]).toHaveTextContent("5.0 ث"); // both times together
    // every line still says who, to a screen reader
    for (const row of rows) expect(row).toHaveTextContent(/كبير مهندسي الكميات|مهندس المراجعة/);
    // the settled line counts the real steps, folded or not
    expect(screen.getByRole("button", { name: /6 خطوات/ })).toBeInTheDocument();
  });
});

describe("every duration and step count reads naturally", () => {
  const S = 1000;
  const M = 60 * S;
  it.each([
    [400, "أقل من ثانية", "under a second"],
    [1 * S, "ثانية", "1s"],
    [2 * S, "ثانيتين", "2s"],
    [3 * S, "3 ثواني", "3s"],
    [10 * S, "10 ثواني", "10s"],
    [11 * S, "11 ثانية", "11s"],
    [59 * S, "59 ثانية", "59s"],
    [1 * M, "دقيقة", "1m"],
    [2 * M, "دقيقتين", "2m"],
    [5 * M, "5 دقايق", "5m"],
    [1 * M + 1 * S, "دقيقة وثانية", "1m 1s"],
    [2 * M + 2 * S, "دقيقتين وثانيتين", "2m 2s"],
    [3 * M + 30 * S, "3 دقايق و30 ثانية", "3m 30s"],
    [15 * M, "15 دقيقة", "15m"],
    [60 * M, "ساعة", "1h"],
    [2 * 60 * M, "ساعتين", "2h"],
    [60 * M + 2 * M, "ساعة ودقيقتين", "1h 2m"],
    [3 * 60 * M + 11 * M, "3 ساعات و11 دقيقة", "3h 11m"],
  ])("%i ms: «%s», “%s”", (ms, ar, en) => {
    expect(duration(ms, "ar")).toBe(ar);
    expect(duration(ms, "en")).toBe(en);
  });

  it("never the colloquial misspelling «تانية»: a second is ثانية", () => {
    for (const ms of [1_000, 2_000, 5_000, 30_000, 62_000]) expect(duration(ms, "ar")).not.toMatch(/تاني/);
  });

  it.each([
    [1, "خطوة واحدة", "1 step"],
    [2, "خطوتين", "2 steps"],
    [3, "3 خطوات", "3 steps"],
    [10, "10 خطوات", "10 steps"],
    [11, "11 خطوة", "11 steps"],
  ])("%i steps: «%s»", (n, ar, en) => {
    expect(count("steps", n, {}, "ar")).toBe(ar);
    expect(count("steps", n, {}, "en")).toBe(en);
  });
});

describe("a Brief with no steps", () => {
  const none: WorklogData = { started: T0, ended: at(2), steps: [] };

  it("says only how long it worked: no step count, no button, no fold arrow", () => {
    render(<ProgressLine items={[]} worklog={none} lang="ar" />);
    expect(screen.getByText("اشتغل ثانيتين")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(document.body).not.toHaveTextContent("مفيش خطوات");
    expect(document.body).not.toHaveTextContent("◂");
    expect(document.body).not.toHaveTextContent("·");
  });

  it("in English too", () => {
    setLanguage("en");
    render(<ProgressLine items={[]} worklog={none} lang="en" />);
    expect(screen.getByText("Worked for 2s")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
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

describe("the steps' keys", () => {
  it("two steps at the same moment by the same agent never share a React key", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const twins: WorklogData = {
      started: T0,
      ended: at(9),
      steps: [step("بيقرا المقايسة", 1, 2), step("بيسعّر البنود", 1, 3), step("بيراجع الأسعار", 1, 9)],
    };
    render(<ProgressLine items={[]} worklog={twins} lang="ar" />);
    fireEvent.click(screen.getAllByRole("button")[0]!);
    expect(screen.getByText("بيراجع الأسعار")).toBeInTheDocument();
    expect(errors.mock.calls.filter((c) => String(c[0]).includes("same key"))).toEqual([]);
    errors.mockRestore();
  });
});
