import { describe, expect, it } from "vitest";
import { place, sizeFor, STRIP_H } from "./place";
import type { Placed } from "./types";

const opts = { gap: 80, rowGap: 120 } as const;

function anyOverlap(frames: Placed[]): boolean {
  return frames.some((a, i) =>
    frames.some((b, j) => j > i && a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h),
  );
}

describe("place", () => {
  it("never overlaps and never moves what is placed", () => {
    const before: Placed[] = [{ key: "files:all", x: 0, y: 0, w: 360, h: 520, z: 0, collapsed: false }];
    const after = place(
      before,
      [
        { key: "deliverable:a", w: 960, h: 640 },
        { key: "deliverable:b", w: 720, h: 900 },
      ],
      { dir: "ltr", ...opts },
    );
    expect(after).toHaveLength(3);
    expect(after[0]).toEqual(before[0]);
    expect(anyOverlap(after)).toBe(false);
  });

  it("English places the next frame to the right, Arabic to the left", () => {
    const incoming = [
      { key: "deliverable:a" as const, w: 960, h: 640 },
      { key: "deliverable:b" as const, w: 720, h: 900 },
    ];
    const [a, b] = place([], incoming, { dir: "ltr", ...opts });
    expect(a!.x + a!.w + 80).toBeLessThanOrEqual(b!.x);
    expect(b!.y).toBe(a!.y);
    const [ra, rb] = place([], incoming, { dir: "rtl", ...opts });
    expect(rb!.x + rb!.w + 80).toBeLessThanOrEqual(ra!.x);
    expect(rb!.y).toBe(ra!.y);
  });

  it("fills a free slot between frames before starting a new row", () => {
    const before: Placed[] = [
      { key: "files:all", x: 0, y: 0, w: 360, h: 520, z: 0, collapsed: false },
      { key: "team:core", x: 1400, y: 0, w: 320, h: 240, z: 0, collapsed: false },
    ];
    const [, , c] = place(before, [{ key: "file:x", w: 480, h: 640 }], { dir: "ltr", ...opts });
    expect(c).toMatchObject({ x: 440, y: 0 });
  });

  it("a key already placed is left where it is", () => {
    const before: Placed[] = [{ key: "files:all", x: 5, y: 5, w: 360, h: 520, z: 3, collapsed: true }];
    expect(place(before, [{ key: "files:all", w: 100, h: 100 }], { dir: "ltr", ...opts })).toEqual(before);
  });

  it("a new frame can start folded", () => {
    const [desk] = place([], [{ key: "desk:p", w: 320, h: 200, collapsed: true }], { dir: "ltr", ...opts });
    expect(desk).toMatchObject({ key: "desk:p", collapsed: true, h: 200 });
  });

  it("a thousand frames are placed without overlap, quickly", () => {
    const incoming = Array.from({ length: 1000 }, (_, i) => ({ key: `deliverable:d${i}` as const, w: 720, h: 560 }));
    const started = performance.now();
    const after = place([], incoming, { dir: "ltr", ...opts });
    expect(performance.now() - started).toBeLessThan(1500);
    expect(after).toHaveLength(1000);
    expect(anyOverlap(after)).toBe(false);
  });

  it("default sizes by kind", () => {
    expect(sizeFor("files:all")).toEqual({ w: 360, h: 520 });
    expect(sizeFor("file:a")).toEqual({ w: 480, h: 640 });
    expect(sizeFor("deliverable:a", { kind: "sheet" })).toEqual({ w: 960, h: 640 });
    expect(sizeFor("deliverable:a", { kind: "document" })).toEqual({ w: 720, h: 900 });
    expect(sizeFor("deliverable:a", { kind: "board" })).toEqual({ w: 720, h: 560 });
    expect(sizeFor("team:core")).toEqual({ w: 320, h: 240 });
    expect(sizeFor("desk:p", { agents: 1 }).w).toBe(320);
    expect(sizeFor("desk:p", { agents: 6 }).h).toBeGreaterThan(sizeFor("desk:p", { agents: 1 }).h);
    expect(sizeFor("desk:p", { agents: 0 }).h).toBeGreaterThanOrEqual(160);
    expect(STRIP_H).toBeLessThan(160);
  });
});
