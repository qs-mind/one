import { describe, expect, it } from "vitest";
import { lod, pickLive } from "./lod";
import type { FrameKey } from "./types";

describe("level of detail", () => {
  it("detail by zoom", () => {
    expect(lod(0.85)).toBe("live");
    expect(lod(0.6)).toBe("live");
    expect(lod(0.45)).toBe("poster");
    expect(lod(0.3)).toBe("poster");
    expect(lod(0.2)).toBe("title");
  });

  it("at most six live viewers, the focused one first", () => {
    const visible = Array.from({ length: 10 }, (_, i) => `deliverable:f${i}` as FrameKey);
    const distance = new Map(visible.map((k, i) => [k, i * 100]));
    const live = pickLive(visible, "deliverable:f9", [], distance);
    expect(live.size).toBe(6);
    expect([...live]).toEqual(["deliverable:f9", ...visible.slice(0, 5)]);
  });

  it("then the selected ones, then the nearest to the centre", () => {
    const visible = Array.from({ length: 10 }, (_, i) => `deliverable:f${i}` as FrameKey);
    const distance = new Map(visible.map((k, i) => [k, i * 100]));
    const live = pickLive(visible, undefined, ["deliverable:f8", "deliverable:f7"], distance, 3);
    expect([...live]).toEqual(["deliverable:f8", "deliverable:f7", "deliverable:f0"]);
  });

  it("never a frame that is not visible", () => {
    const live = pickLive(["deliverable:a"], "deliverable:far", ["deliverable:b"], new Map());
    expect([...live]).toEqual(["deliverable:a"]);
  });
});
