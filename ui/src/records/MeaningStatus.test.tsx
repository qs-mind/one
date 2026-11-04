import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { formatBytes, MeaningStatus } from "./MeaningStatus";

const project = "p1";
const total = 1_173_349_509; // the two pinned search models, as the core's manifest says

type Model = { state: string; done_bytes?: number; total_bytes?: number; reason?: { en: string; ar: string } | null };
type Job = { state: string; done: number; total: number; reason?: { en: string; ar: string } | null };

// GET /api/meaning as the core answers it.
function status(model: Model, job?: Job, paused = false) {
  return {
    model: { done_bytes: 0, total_bytes: total, reason: null, ...model },
    indexing: { paused, projects: job ? { [project]: { reason: null, ...job } } : {} },
  };
}

// The core behind /api: `answer` gives the current GET /api/meaning body; every POST is recorded.
function core(answer: () => object | undefined) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    if (url === "/api/meaning" && (init.method ?? "GET") === "GET") {
      const body = answer();
      return body ? Response.json(body) : new Response("down", { status: 500 });
    }
    if (url.startsWith("/api/meaning/") && init.method === "POST") return Response.json(answer(), { status: 202 });
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const gets = (fetch: ReturnType<typeof core>) =>
  fetch.mock.calls.filter(([url, init]) => url === "/api/meaning" && (init?.method ?? "GET") === "GET").length;
const posted = (fetch: ReturnType<typeof core>) =>
  fetch.mock.calls.filter(([, init]) => init?.method === "POST").map(([url]) => String(url));

beforeEach(() => setLanguage("ar"));
afterEach(() => vi.useRealTimers());

describe("formatBytes", () => {
  it("gives MB under a gigabyte and GB with one decimal above, the same in both languages", () => {
    expect(formatBytes(420_000_000)).toBe("420 MB");
    expect(formatBytes(total)).toBe("1.2 GB");
    expect(formatBytes(0)).toBe("0 MB");
  });
});

describe("MeaningStatus", () => {
  it("offers the download with its real size and starts it", async () => {
    let now = status({ state: "off" });
    const fetch = core(() => now);
    const user = userEvent.setup();
    render(<MeaningStatus projectId={project} />);

    const line = await screen.findByText(texts.meaningOff.ar.replace("{size}", "1.2 GB"));
    expect(line).toHaveAttribute("role", "status");
    now = status({ state: "downloading", done_bytes: 0 });
    await user.click(screen.getByRole("button", { name: texts.meaningDownload.ar }));

    expect(posted(fetch)).toEqual(["/api/meaning/download"]);
    expect(await screen.findByRole("button", { name: texts.meaningStop.ar })).toBeInTheDocument();
  });

  it("shows download progress and stops it", async () => {
    let now = status({ state: "downloading", done_bytes: 420_000_000 });
    const fetch = core(() => now);
    const user = userEvent.setup();
    render(<MeaningStatus projectId={project} />);

    expect(await screen.findByText("جارٍ تنزيل نموذج البحث: 420 MB من 1.2 GB")).toHaveAttribute("role", "status");
    now = status({ state: "stopped", done_bytes: 420_000_000 });
    await user.click(screen.getByRole("button", { name: texts.meaningStop.ar }));

    expect(posted(fetch)).toEqual(["/api/meaning/stop"]);
    expect(await screen.findByText("توقّف التنزيل عند 420 MB من 1.2 GB.")).toBeInTheDocument();
    now = status({ state: "downloading", done_bytes: 420_000_000 });
    await user.click(screen.getByRole("button", { name: texts.meaningResume.ar }));
    expect(posted(fetch)).toEqual(["/api/meaning/stop", "/api/meaning/download"]);

    setLanguage("en");
    expect(await screen.findByRole("button", { name: texts.meaningStop.en })).toBeInTheDocument();
  });

  it("polls while something moves and stops when ready", async () => {
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
    expect(screen.getByText(texts.meaningReady.ar)).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(gets(fetch)).toBe(5);
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

  it("shows the core's reason and tries again after a failure", async () => {
    const noInternet = { en: "The search model did not download. Try again.", ar: "نموذج البحث ما اتنزلش. جرّب تاني." };
    let now = status({ state: "failed", done_bytes: 9, reason: noInternet });
    const fetch = core(() => now);
    const user = userEvent.setup();
    render(<MeaningStatus projectId={project} />);

    expect(await screen.findByText(noInternet.ar)).toHaveAttribute("role", "status");
    now = status({ state: "downloading", done_bytes: 9 });
    await user.click(screen.getByRole("button", { name: texts.meaningRetry.ar }));
    expect(posted(fetch)).toEqual(["/api/meaning/download"]);
  });

  it("says plainly when this computer cannot run it, with no button", async () => {
    const cannot = { en: "Search by meaning cannot run on this computer.", ar: "البحث بالمعنى مش هينفع هنا." };
    core(() => status({ state: "unavailable", reason: cannot }));
    render(<MeaningStatus projectId={project} />);
    expect(await screen.findByText(cannot.ar)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says the files are being checked, with no button", async () => {
    core(() => status({ state: "checking", done_bytes: total }));
    render(<MeaningStatus projectId={project} />);
    expect(await screen.findByText(texts.meaningChecking.ar)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows indexing N of M and pauses it", async () => {
    let now = status({ state: "ready", done_bytes: total }, { state: "indexing", done: 120, total: 400 });
    const fetch = core(() => now);
    const user = userEvent.setup();
    render(<MeaningStatus projectId={project} />);

    expect(await screen.findByText("جارٍ تجهيز البحث بالمعنى: 120 من 400 جزء")).toBeInTheDocument();
    now = status({ state: "ready", done_bytes: total }, { state: "indexing", done: 124, total: 400 }, true);
    await user.click(screen.getByRole("button", { name: texts.meaningPause.ar }));

    expect(posted(fetch)).toEqual(["/api/meaning/pause"]);
    expect(await screen.findByText("متوقف مؤقتًا عند 124 من 400 جزء.")).toBeInTheDocument();
    now = status({ state: "ready", done_bytes: total }, { state: "ready", done: 400, total: 400 });
    await user.click(screen.getByRole("button", { name: texts.meaningResume.ar }));
    expect(posted(fetch)).toEqual(["/api/meaning/pause", "/api/meaning/resume"]);
    expect(await screen.findByText(texts.meaningReady.ar)).toHaveClass("text-slate");
  });

  it("a project whose preparing failed says why and tries again by resuming", async () => {
    const stopped = { en: "Preparing search by meaning stopped on this project.", ar: "تجهيز البحث بالمعنى وقف." };
    const fetch = core(() =>
      status({ state: "ready", done_bytes: total }, { state: "failed", done: 3, total: 9, reason: stopped }),
    );
    const user = userEvent.setup();
    render(<MeaningStatus projectId={project} />);
    expect(await screen.findByText(stopped.ar)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.meaningRetry.ar }));
    expect(posted(fetch)).toEqual(["/api/meaning/resume"]);
  });

  it("shows nothing when the core does not answer", async () => {
    const fetch = core(() => undefined);
    render(<MeaningStatus projectId={project} />);
    await waitFor(() => expect(gets(fetch)).toBe(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("every new label exists in both languages, with the same blanks", () => {
    for (const key of [
      "meaningOff",
      "meaningDownload",
      "meaningDownloading",
      "meaningStop",
      "meaningStopped",
      "meaningResume",
      "meaningChecking",
      "meaningRetry",
      "meaningIndexing",
      "meaningPause",
      "meaningPaused",
      "meaningReady",
      "reordering",
    ] as const) {
      const { en, ar } = texts[key];
      expect(en.trim()).not.toBe("");
      expect(ar.trim()).not.toBe("");
      expect(en).not.toBe(ar);
      const blanks = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();
      expect(blanks(ar)).toEqual(blanks(en));
      expect(en).not.toMatch(/\blocal\b/i); // the glossary bans it for on-device things
      expect(ar).not.toContain("محلي");
    }
  });
});
