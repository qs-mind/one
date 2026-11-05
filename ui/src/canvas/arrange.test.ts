import { describe, expect, it } from "vitest";
import { arrange } from "./arrange";
import type { DeliverableInfo, FrameKey, Placed } from "../project/types";

const frame = (key: FrameKey, x: number, y: number, w = 400, h = 300): Placed => ({ key, x, y, w, h, z: 0, collapsed: false });
const status = new Map<FrameKey, DeliverableInfo["status"]>([
  ["deliverable:s", "signed_off"],
  ["deliverable:c", "checked"],
  ["deliverable:d", "draft"],
]);

/** Keys in reading order: by row (a frame starts a new row when it is below half the row's height), then by side. */
function reading(frames: Placed[], dir: "ltr" | "rtl"): FrameKey[] {
  const sorted = [...frames].sort((a, b) => a.y - b.y);
  const rows: Placed[][] = [];
  for (const f of sorted) {
    const row = rows.at(-1);
    if (row && f.y < row[0]!.y + row[0]!.h / 2) row.push(f);
    else rows.push([f]);
  }
  return rows.flatMap((row) => row.sort((a, b) => (dir === "ltr" ? a.x - b.x : b.x - a.x)).map((f) => f.key));
}

describe("arrange", () => {
  const frames = [
    frame("team:core", 0, 0),
    frame("deliverable:s", 900, 900),
    frame("deliverable:c", 300, 2000),
    frame("files:all", 2000, 50),
    frame("deliverable:d", -500, 400),
    frame("file:f1", 40, 3000),
  ];

  it("stage puts files, then drafts, then checked, then signed off, then the team", () => {
    const out = arrange(frames, status, "stage", { dir: "ltr" });
    const x = (key: FrameKey) => out.find((f) => f.key === key)!.x;
    expect(x("files:all")).toBe(x("file:f1"));
    expect(x("files:all")).toBeLessThan(x("deliverable:d"));
    expect(x("deliverable:d")).toBeLessThan(x("deliverable:c"));
    expect(x("deliverable:c")).toBeLessThan(x("deliverable:s"));
    expect(x("deliverable:s")).toBeLessThan(x("team:core"));
  });

  it("stage runs right to left in Arabic", () => {
    const out = arrange(frames, status, "stage", { dir: "rtl" });
    const x = (key: FrameKey) => out.find((f) => f.key === key)!.x;
    expect(x("files:all")).toBeGreaterThan(x("deliverable:d"));
    expect(x("deliverable:s")).toBeGreaterThan(x("team:core"));
  });

  it("tidy keeps the reading order", () => {
    for (const dir of ["ltr", "rtl"] as const) {
      const out = arrange(frames, status, "tidy", { dir });
      expect(reading(out, dir)).toEqual(reading(frames, dir));
    }
  });

  it("returns a new layout with the same frames and sizes, and leaves the old one alone", () => {
    const copy = structuredClone(frames);
    const out = arrange(frames, status, "tidy", { dir: "ltr" });
    expect(frames).toEqual(copy);
    expect(out.map((f) => [f.key, f.w, f.h]).sort()).toEqual(frames.map((f) => [f.key, f.w, f.h]).sort());
  });
});
