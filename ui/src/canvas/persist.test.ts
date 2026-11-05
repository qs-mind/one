import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fakeSources } from "../project/fake";
import { createSaver } from "./persist";
import type { Placed } from "../project/types";

const at = (x: number): Placed => ({ key: "deliverable:a", x, y: 0, w: 960, h: 640, z: 0, collapsed: false });

describe("saving the layout", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("three moves of one frame make one save with the last position", async () => {
    const fake = fakeSources({});
    const saver = createSaver(fake);
    saver.frames([at(1)], []);
    await vi.advanceTimersByTimeAsync(300);
    saver.frames([at(2)], []);
    await vi.advanceTimersByTimeAsync(300);
    saver.frames([at(3)], []);
    await vi.advanceTimersByTimeAsync(499);
    expect(fake.saved.frames).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(fake.saved.frames).toEqual([{ frames: [at(3)], removed: [], keepalive: false }]);
  });

  it("a removed frame is sent once, and a frame placed again is no longer removed", async () => {
    const fake = fakeSources({});
    const saver = createSaver(fake);
    saver.frames([], ["file:x", "file:y"]);
    saver.frames([{ ...at(0), key: "file:y" }], []);
    await vi.advanceTimersByTimeAsync(500);
    expect(fake.saved.frames).toEqual([{ frames: [{ ...at(0), key: "file:y" }], removed: ["file:x"], keepalive: false }]);
  });

  it("the view waits a second after the last pan or zoom", async () => {
    const fake = fakeSources({});
    const saver = createSaver(fake);
    saver.view({ x: 1, y: 1, zoom: 1 });
    await vi.advanceTimersByTimeAsync(900);
    saver.view({ x: 2, y: 2, zoom: 0.5 });
    await vi.advanceTimersByTimeAsync(999);
    expect(fake.saved.views).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(fake.saved.views).toEqual([{ view: { x: 2, y: 2, zoom: 0.5 }, keepalive: false }]);
  });

  it("flush sends at once with keepalive, and then nothing is left to send", async () => {
    const fake = fakeSources({});
    const saver = createSaver(fake);
    saver.frames([at(4)], []);
    saver.view({ x: 3, y: 3, zoom: 0.85 });
    saver.flush(true);
    expect(fake.saved.frames).toEqual([{ frames: [at(4)], removed: [], keepalive: true }]);
    expect(fake.saved.views).toEqual([{ view: { x: 3, y: 3, zoom: 0.85 }, keepalive: true }]);
    await vi.advanceTimersByTimeAsync(2000);
    expect(fake.saved.frames).toHaveLength(1);
    expect(fake.saved.views).toHaveLength(1);
  });

  it("a failed save is sent again with the next one", async () => {
    const fake = fakeSources({});
    const failing = vi.spyOn(fake, "saveFrames").mockRejectedValueOnce(new Error("core down"));
    const saver = createSaver(fake);
    saver.frames([at(5)], []);
    await vi.advanceTimersByTimeAsync(500);
    saver.frames([{ ...at(0), key: "file:b" }], []);
    await vi.advanceTimersByTimeAsync(500);
    expect(failing).toHaveBeenCalledTimes(2);
    expect(failing.mock.calls[1]![0]).toEqual([at(5), { ...at(0), key: "file:b" }]);
  });

  it("never writes to web storage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const fake = fakeSources({});
    const saver = createSaver(fake);
    saver.frames([at(1)], ["file:gone"]);
    saver.view({ x: 0, y: 0, zoom: 1 });
    await vi.advanceTimersByTimeAsync(1000);
    saver.flush(true);
    expect(fake.saved.frames.length).toBeGreaterThan(0);
    expect(spy).not.toHaveBeenCalled();
  });
});
