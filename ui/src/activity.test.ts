import { afterEach, describe, expect, it, vi } from "vitest";
import { subscribeActivity, subscribeGeneral, subscribeTender } from "./activity";
import type { GeneralActivity, TenderActivity } from "./api/client";
import type { ActivityEvent } from "./project/types";

// A fetch whose each call answers a stream the test writes to and closes.
function streamingFetch() {
  const calls: { url: string; signal: AbortSignal; write(text: string): void; close(): void }[] = [];
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({ start: (c) => void (controller = c) });
    const signal = init.signal!;
    signal.addEventListener("abort", () => controller.error(new DOMException("aborted", "AbortError")));
    calls.push({
      url,
      signal,
      write: (text) => controller.enqueue(new TextEncoder().encode(text)),
      close: () => controller.close(),
    });
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  });
  vi.stubGlobal("fetch", fetch);
  return { fetch, calls };
}

const waiting = (count: number): ActivityEvent => ({ type: "waiting", count });
const line = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`;
const settle = () => vi.advanceTimersByTimeAsync(0);

afterEach(() => vi.useRealTimers());

describe("subscribeActivity", () => {
  it("two subscribers share one stream and both get each event", async () => {
    vi.useFakeTimers();
    const { fetch, calls } = streamingFetch();
    const a: ActivityEvent[] = [];
    const b: ActivityEvent[] = [];
    const stopA = subscribeActivity("p1", (e) => a.push(e));
    const stopB = subscribeActivity("p1", (e) => b.push(e));
    await settle();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(calls[0]!.url).toBe("/api/projects/p1/activity");
    calls[0]!.write(line(waiting(2)));
    await settle();
    expect(a).toEqual([waiting(2)]);
    expect(b).toEqual([waiting(2)]);
    stopA();
    stopB();
  });

  it("an event split across chunks arrives whole", async () => {
    vi.useFakeTimers();
    const { calls } = streamingFetch();
    const got: ActivityEvent[] = [];
    const stop = subscribeActivity("p2", (e) => got.push(e));
    await settle();
    const text = line({ type: "agent-gone", id: "run1" });
    calls[0]!.write(text.slice(0, 9));
    await settle();
    expect(got).toEqual([]);
    calls[0]!.write(text.slice(9).replace("\n\n", "\r\n\r\n"));
    await settle();
    expect(got).toEqual([{ type: "agent-gone", id: "run1" }]);
    stop();
  });

  it("pings, bad JSON and unknown types are skipped", async () => {
    vi.useFakeTimers();
    const { calls } = streamingFetch();
    const got: ActivityEvent[] = [];
    const stop = subscribeActivity("p3", (e) => got.push(e));
    await settle();
    const file = { type: "file", file: { id: "f1", name: "جدول - عينة.xlsx", status: "read", note: null, replaces: null } };
    const boq = { type: "client_boq", client_boq: { file_id: "f1", name: "جدول - عينة.xlsx", items: 2, headings: 1, at: "2026-11-05T09:00:00+00:00" } };
    calls[0]!.write(
      ": ping\n\n" + "data: {not json\n\n" + line({ type: "mystery", x: 1 }) + line({ type: "agent" }) + line({ type: "file" }) + line(waiting(1)) + line(file) +
        line({ type: "client_boq" }) + line(boq),
    );
    await settle();
    expect(got).toEqual([waiting(1), file, boq]); // a file added to Project Records, a client BOQ imported
    stop();
  });

  it("a dropped stream reconnects after 1 s and says so; later drops wait longer", async () => {
    vi.useFakeTimers();
    const { fetch, calls } = streamingFetch();
    const reconnected = vi.fn();
    const stop = subscribeActivity("p4", () => {}, reconnected);
    await settle();
    calls[0]!.close();
    await vi.advanceTimersByTimeAsync(999);
    expect(fetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(reconnected).toHaveBeenCalledOnce();
    stop();
  });

  it("a core that does not answer is tried after 1, 2, 5, then every 10 s", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn(async () => new Response(null, { status: 404 }));
    vi.stubGlobal("fetch", fetch);
    const stop = subscribeActivity("p5", () => {});
    await settle();
    const at: number[] = [];
    for (const step of [1000, 2000, 5000, 10000, 10000]) {
      await vi.advanceTimersByTimeAsync(step);
      at.push(fetch.mock.calls.length);
    }
    expect(at).toEqual([2, 3, 4, 5, 6]);
    stop();
  });

  it("the last unsubscribe aborts the fetch, and a new one starts afresh", async () => {
    vi.useFakeTimers();
    const { fetch, calls } = streamingFetch();
    const stopA = subscribeActivity("p6", () => {});
    const stopB = subscribeActivity("p6", () => {});
    await settle();
    stopA();
    expect(calls[0]!.signal.aborted).toBe(false);
    stopB();
    expect(calls[0]!.signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(20000);
    expect(fetch).toHaveBeenCalledTimes(1);
    const stopC = subscribeActivity("p6", () => {});
    await settle();
    expect(fetch).toHaveBeenCalledTimes(2);
    stopC();
  });
});

// The Phase 1 contract's events travel on the same stream. Synthetic «عينة» data only.
describe("the contract's events", () => {
  const brief: TenderActivity = { type: "brief", brief_id: "5a".padEnd(32, "0"), state: "running" };
  const noPlan: TenderActivity = { type: "plan", plan: null };

  it("a tender's events and today's share one stream, and each listener gets its own", async () => {
    vi.useFakeTimers();
    const { fetch, calls } = streamingFetch();
    const old: ActivityEvent[] = [];
    const tender: TenderActivity[] = [];
    const stopOld = subscribeActivity("p7", (e) => old.push(e));
    const stopTender = subscribeTender("p7", (e) => tender.push(e));
    await settle();
    expect(fetch).toHaveBeenCalledTimes(1);
    calls[0]!.write(line(brief) + line(waiting(1)) + line(noPlan) + line({ type: "home" }));
    await settle();
    expect(tender).toEqual([brief, noPlan]); // a plan that is gone is said too; `home` belongs to no tender
    expect(old).toEqual([waiting(1)]);
    stopOld();
    expect(calls[0]!.signal.aborted).toBe(false);
    stopTender();
    expect(calls[0]!.signal.aborted).toBe(true);
  });

  it("the events of no tender arrive on the general stream", async () => {
    vi.useFakeTimers();
    const { calls } = streamingFetch();
    const got: GeneralActivity[] = [];
    const reconnected = vi.fn();
    const stop = subscribeGeneral((e) => got.push(e), reconnected);
    await settle();
    expect(calls[0]!.url).toBe("/api/projects/general/activity");
    calls[0]!.write(line({ type: "home" }) + line(brief) + line({ type: "lessons" }));
    await settle();
    expect(got).toEqual([{ type: "home" }, { type: "lessons" }]);
    calls[0]!.close();
    await vi.advanceTimersByTimeAsync(1000);
    expect(reconnected).toHaveBeenCalledOnce(); // the listener then loads its routes again
    stop();
  });

  it("an event without what it must carry is skipped", async () => {
    vi.useFakeTimers();
    const { calls } = streamingFetch();
    const got: TenderActivity[] = [];
    const stop = subscribeTender("p8", (e) => got.push(e));
    await settle();
    calls[0]!.write(
      line({ type: "plan" }) + line({ type: "finding" }) + line({ type: "room", room: {} }) + line({ type: "brief", state: "running" }) +
        line({ type: "constructor" }) + line(brief),
    );
    await settle();
    expect(got).toEqual([brief]);
    stop();
  });
});
