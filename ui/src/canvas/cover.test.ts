import { describe, expect, it } from "vitest";
import { freeRect, worldOf } from "./cover";
import { inView, placeInView } from "./place";
import type { Placed } from "./types";

// The canvas pane at 1440 × 852 under the top bar, as the founder's window had it.
const pane = { x: 0, y: 48, w: 1440, h: 852 };
const chatEnglish = { x: 1084, y: 56, w: 340, h: 824 }; // the inline end, the right
const chatArabic = { x: 16, y: 56, w: 340, h: 824 }; // the left
const minimap = { x: 16, y: 600, w: 200, h: 150 };
const commandBar = { x: 272, y: 820, w: 560, h: 64 };

describe("the free area of the canvas", () => {
  it("leaves out the open chat on its side, in English and in Arabic", () => {
    expect(freeRect(pane, [chatEnglish])).toEqual({ x: 0, y: 0, w: 1084, h: 852 });
    expect(freeRect(pane, [chatArabic])).toEqual({ x: 356, y: 0, w: 1084, h: 852 });
  });

  it("leaves out a band over the minimap and the command bar at the bottom", () => {
    const free = freeRect(pane, [chatEnglish, minimap, commandBar]);
    expect(free).toEqual({ x: 0, y: 0, w: 1084, h: 552 }); // up to the minimap's top edge
  });

  it("with the chat a sheet over everything, the whole pane is used", () => {
    expect(freeRect(pane, [{ x: 0, y: 48, w: 1440, h: 852 }])).toEqual({ x: 0, y: 0, w: 1440, h: 852 });
  });

  it("reads the free area in world coordinates under the viewport", () => {
    expect(worldOf({ x: 100, y: 0, w: 800, h: 600 }, [-200, 50, 2])).toEqual({ x: 150, y: -25, w: 400, h: 300 });
  });
});

describe("a new frame in the visible free area", () => {
  const opts = { dir: "ltr" as const, gap: 80, rowGap: 120 };
  const files: Placed = { key: "files:all", x: 0, y: 0, w: 360, h: 520, z: 0, collapsed: false };
  const view = { x: -100, y: -100, w: 1300, h: 900 };

  it("goes in the view beside what is there, never under it, from the start side", () => {
    const p = placeInView([files], { key: "file:f1", w: 480, h: 640 }, view, opts)!;
    expect(inView(p, view)).toBe(true);
    expect(p.x).toBeGreaterThanOrEqual(files.x + files.w + 80);
    const rtl = placeInView([files], { key: "file:f1", w: 480, h: 640 }, view, { ...opts, dir: "rtl" })!;
    expect(inView(rtl, view)).toBe(true);
    expect(rtl.x + rtl.w).toBe(view.x + view.w - 80); // Arabic starts at the right
  });

  it("is null when it cannot fit there: the canvas places it and brings it into view", () => {
    expect(placeInView([files], { key: "file:f1", w: 480, h: 640 }, { x: 0, y: 0, w: 500, h: 500 }, opts)).toBeNull();
  });
});
