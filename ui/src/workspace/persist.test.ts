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
