import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../i18n";
import { MeaningStatus } from "./MeaningStatus";

const project = "p1";
const total = 135_390_915; // the pinned search model, as the core's manifest says

type Model = { state: string; done_bytes?: number; total_bytes?: number; reason?: { en: string; ar: string } | null };
type Job = { state: string; done: number; total: number; reason?: { en: string; ar: string } | null };

// GET /api/meaning as the core answers it.
function status(model: Model, job?: Job) {
  return {
    model: { done_bytes: 0, total_bytes: total, reason: null, ...model },
    indexing: { projects: job ? { [project]: { reason: null, ...job } } : {} },
  };
}

// The core behind /api: `answer` gives the current GET /api/meaning body.
function core(answer: () => object | undefined) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/meaning") {
      const body = answer();
      return body ? Response.json(body) : new Response("down", { status: 500 });
    }
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const gets = (fetch: ReturnType<typeof core>) => fetch.mock.calls.length;
const preparing = (percent: string, lang: "en" | "ar" = "ar") => fill(texts.meaningPreparing[lang], { percent });

beforeEach(() => setLanguage("ar"));
afterEach(() => vi.useRealTimers());

describe("MeaningStatus", () => {
  it("shows one quiet Slate line with the download's percent, and no button", async () => {
    core(() => status({ state: "downloading", done_bytes: 57_000_000 }));
    render(<MeaningStatus projectId={project} />);
    const line = await screen.findByText(preparing("42%"));
    expect(line).toHaveAttribute("role", "status");
    expect(line).toHaveClass("text-slate");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    setLanguage("en");
    expect(await screen.findByText(preparing("42%", "en"))).toBeInTheDocument();
  });

  it("keeps the same line while the files are checked, then for this project's preparing", async () => {
    let now = status({ state: "checking", done_bytes: total });
    core(() => now);
    vi.useFakeTimers();
    render(<MeaningStatus projectId={project} />);
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(preparing("100%"))).toBeInTheDocument();
    now = status({ state: "ready", done_bytes: total }, { state: "indexing", done: 120, total: 400 });
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByText(preparing("30%"))).toBeInTheDocument();
  });

  it("shows nothing once ready, and stops polling", async () => {
    vi.useFakeTimers();
    let now = status({ state: "downloading", done_bytes: 1 });
    const fetch = core(() => now);
    render(<MeaningStatus projectId={project} />);
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(gets(fetch)).toBe(1);
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(gets(fetch)).toBe(4); // three polls in three seconds

    now = status({ state: "ready", done_bytes: total }, { state: "ready", done: 5, total: 5 });
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(gets(fetch)).toBe(5);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(gets(fetch)).toBe(5);
  });

  it("shows nothing before a project has a file, and looks again when one comes", async () => {
    vi.useFakeTimers();
    let now = status({ state: "off" });
    const fetch = core(() => now);
    const { rerender } = render(<MeaningStatus projectId={project} files={0} />);
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(gets(fetch)).toBe(1); // nothing moves: no polling
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    rerender(<MeaningStatus projectId={project} files={1} />);
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(gets(fetch)).toBe(2);
    now = status({ state: "downloading", done_bytes: 0 }); // the core started on the file
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByText(preparing("0%"))).toBeInTheDocument();
  });

  it("after a file comes in with the model ready, keeps looking until the project's preparing shows", async () => {
    vi.useFakeTimers();
    let now = status({ state: "ready", done_bytes: total }, { state: "ready", done: 5, total: 5 });
    const fetch = core(() => now);
    const { rerender } = render(<MeaningStatus projectId={project} files={1} />);
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    rerender(<MeaningStatus projectId={project} files={2} />); // the core has not looked at it yet
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    now = status({ state: "ready", done_bytes: total }, { state: "indexing", done: 5, total: 45 });
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByText(preparing("11%"))).toBeInTheDocument();

    now = status({ state: "ready", done_bytes: total }, { state: "ready", done: 45, total: 45 });
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    const polls = gets(fetch);
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(gets(fetch)).toBe(polls); // done: no more waiting
  });

  it("gives up waiting after a few seconds when a file starts nothing (no text in it)", async () => {
    vi.useFakeTimers();
    const fetch = core(() => status({ state: "off" }));
    render(<MeaningStatus projectId={project} files={1} />);
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(gets(fetch)).toBe(11);
  });

  it("stops polling when the panel closes", async () => {
    vi.useFakeTimers();
    const fetch = core(() => status({ state: "ready" }, { state: "indexing", done: 1, total: 9 }));
    const { unmount } = render(<MeaningStatus projectId={project} />);
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(gets(fetch)).toBe(3);
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(gets(fetch)).toBe(3);
  });

  it("says plainly when it is not ready after a failure, with no button and no retry here", async () => {
    vi.useFakeTimers();
    const why = { en: "The search model did not download.", ar: "نموذج البحث مانزلش." };
    const fetch = core(() => status({ state: "failed", done_bytes: 9, reason: why }));
    render(<MeaningStatus projectId={project} />);
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(texts.meaningNotReady.ar)).toHaveClass("text-slate");
    expect(screen.queryByText(why.ar)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(gets(fetch)).toBe(1); // it tries again at the next start, by itself
  });

  it("says the same when this project's preparing failed", async () => {
    core(() => status({ state: "ready", done_bytes: total }, { state: "failed", done: 3, total: 9 }));
    render(<MeaningStatus projectId={project} />);
    expect(await screen.findByText(texts.meaningNotReady.ar)).toBeInTheDocument();
  });

  it("shows nothing on a computer that cannot run it, or when the core does not answer", async () => {
    const cannot = { en: "Search by meaning cannot run on this computer.", ar: "البحث بالمعنى مش هينفع هنا." };
    let fetch = core(() => status({ state: "unavailable", reason: cannot }));
    const { unmount } = render(<MeaningStatus projectId={project} />);
    await waitFor(() => expect(gets(fetch)).toBe(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    unmount();

    fetch = core(() => undefined);
    render(<MeaningStatus projectId={project} />);
    await waitFor(() => expect(gets(fetch)).toBe(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("its two labels exist in both languages, with the same blanks, and say nothing of a download", () => {
    for (const key of ["meaningPreparing", "meaningNotReady"] as const) {
      const { en, ar } = texts[key];
      expect(en.trim()).not.toBe("");
      expect(ar.trim()).not.toBe("");
      expect(en).not.toBe(ar);
      const blanks = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();
      expect(blanks(ar)).toEqual(blanks(en));
      expect(en).not.toMatch(/\blocal\b|Hugging Face|download/i);
      expect(ar).not.toMatch(/محلي|Hugging Face|تنزيل/);
    }
    for (const gone of ["meaningOff", "meaningDownload", "meaningStop", "meaningPause", "reordering"])
      expect(gone in texts).toBe(false);
  });
});
