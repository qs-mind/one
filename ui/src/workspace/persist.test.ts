import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fakeSources } from "../project/fake";
import { createWorkspaceSaver } from "./persist";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("createWorkspaceSaver", () => {
  it("three opens within 500 ms send one save with the last", () => {
    const s = fakeSources({});
    const saver = createWorkspaceSaver(s);
    saver.save({ key: "file:a", anchor: null });
    vi.advanceTimersByTime(300);
    saver.save({ key: "file:b", anchor: null });
    vi.advanceTimersByTime(300);
    saver.save({ key: "file:c", anchor: { page: 1 } });
    vi.advanceTimersByTime(499);
    expect(s.saved.workspace).toHaveLength(0);
    vi.advanceTimersByTime(1);
    expect(s.saved.workspace).toEqual([{ opened: { key: "file:c", anchor: { page: 1 } }, keepalive: false }]);
  });

  it("flushes the open document to its own project on switch", () => {
    const first = fakeSources({});
    const second = fakeSources({});
    const a = createWorkspaceSaver(first);
    const b = createWorkspaceSaver(second);
    a.save({ key: "file:a", anchor: null });
    a.flush();
    b.save({ key: "file:b", anchor: null });
    expect(first.saved.workspace).toEqual([{ opened: { key: "file:a", anchor: null }, keepalive: false }]);
    expect(second.saved.workspace).toHaveLength(0);
    vi.advanceTimersByTime(500);
    expect(first.saved.workspace).toHaveLength(1);
    expect(second.saved.workspace).toHaveLength(1);
  });

  it("flush resolves once every save sent so far is answered, the one already on its way too", async () => {
    vi.useRealTimers();
    const answered: string[] = [];
    let answer!: () => void;
    const saver = createWorkspaceSaver({
      saveWorkspace: (opened) =>
        new Promise<void>((resolve) => {
          answer = () => {
            answered.push(opened.key);
            resolve();
          };
        }),
    }, 0);
    saver.save({ key: "file:a", anchor: null });
    await new Promise((resolve) => setTimeout(resolve, 5)); // the save went by itself: it is on its way
    let done = false;
    const flushed = saver.flush().then(() => void (done = true));
    await Promise.resolve();
    expect(done).toBe(false); // still waiting for the core
    answer();
    await flushed;
    expect(answered).toEqual(["file:a"]);
  });

  it("sends the anchor as it was when saved, not as it moves on after", () => {
    const s = fakeSources({});
    const saver = createWorkspaceSaver(s);
    const opened = { key: "file:a" as const, anchor: { page: 2 } };
    saver.save(opened);
    saver.flush();
    opened.anchor = { page: 5 };
    expect(s.saved.workspace[0]!.opened).toEqual({ key: "file:a", anchor: { page: 2 } });
  });

  it("flush with keepalive sends what waits, once", () => {
    const s = fakeSources({});
    const saver = createWorkspaceSaver(s);
    saver.flush(true);
    saver.save({ key: "file:a", anchor: null });
    saver.flush(true);
    saver.flush(true);
    expect(s.saved.workspace).toEqual([{ opened: { key: "file:a", anchor: null }, keepalive: true }]);
  });
});
