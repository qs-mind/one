import { describe, expect, it } from "vitest";
import { freeRect, readable, revealed, READABLE, worldOf } from "./cover";
import { inView, placeInView } from "./place";
import type { Placed } from "../project/types";

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

  it("leaves out a band at the minimap and the command bar, whichever way leaves more room", () => {
    // the command bar: a band off the bottom; the minimap then: its side, not another band across
    expect(freeRect(pane, [chatEnglish, minimap, commandBar])).toEqual({ x: 216, y: 0, w: 868, h: 772 });
    // a wide band at the bottom alone is taken off across
    expect(freeRect(pane, [{ x: 0, y: 800, w: 1440, h: 48 }])).toEqual({ x: 0, y: 0, w: 1440, h: 752 });
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

describe("a first view stays readable", () => {
  const frames = [
    { key: "files:all", x: 0, y: 0, w: 360, h: 520 },
    { key: "deliverable:old", x: 440, y: 0, w: 960, h: 640 },
    { key: "deliverable:new", x: 1480, y: 0, w: 960, h: 640 },
    { key: "team:core", x: 0, y: 760, w: 480, h: 400 },
  ];
  const rank = (key: string) => ["deliverable:new", "files:all", "deliverable:old", "team:core"].indexOf(key);

  it("shows them all when they fit at a readable zoom", () => {
    expect(readable(frames, rank, { w: 3000, h: 2000 })).toHaveLength(4);
  });

  it("else the ones that matter most, as many as fit at 60%", () => {
    // 1084 × 852 beside the chat: 60% leaves room for about 1440 world px across
    const shown = readable(frames, rank, { w: 1084, h: 852 }).map((f) => f.key);
    expect(shown[0]).toBe("deliverable:new");
    expect(shown).not.toContain("files:all"); // too far from the newest to be read with it
    expect(shown).toEqual(["deliverable:new"]);
    const near = readable(frames, (k) => ["files:all", "deliverable:old", "deliverable:new", "team:core"].indexOf(k), { w: 1626, h: 1278 });
    expect(near.map((f) => f.key)).toEqual(["files:all", "deliverable:old", "team:core"]);
  });
});

describe("a frame that arrives out of view (tender day: the BOQ frame came, the view went to 79% and the Team frame sat half off)", () => {
  const box = (key: string, x: number, y: number, w: number, h: number) => ({ key, x, y, w, h });
  const area = { w: 1060, h: 780 };

  it("is shown with the frames that were in view, whole, while they fit at a readable zoom", () => {
    const team = box("team:core", 0, 0, 420, 300);
    const files = box("files:all", 460, 0, 380, 300);
    const boq = box("deliverable:boq", 0, 340, 900, 420);
    const shown = revealed([boq], [files, team], [], area)!;
    expect(shown[0]!.key).toBe("deliverable:boq");
    expect(shown.map((f) => f.key).sort()).toEqual(["deliverable:boq", "files:all", "team:core"]);
  });

  it("frames only partly in view come along nearest first, while all stay readable; the new frame always", () => {
    const boq = box("deliverable:boq", 0, 0, 1200, 700);
    const near = box("team:core", 0, -340, 400, 300);
    const far = box("files:all", 3000, 0, 400, 300);
    const shown = revealed([boq], [], [far, near], area)!;
    expect(shown.map((f) => f.key)).toEqual(["deliverable:boq", "team:core"]);
    const w = Math.max(...shown.map((f) => f.x + f.w)) - Math.min(...shown.map((f) => f.x));
    expect((area.w - 64) / w).toBeGreaterThanOrEqual(READABLE);
  });

  it("too far to show with the frames wholly in view: the view stays, so none of them leaves (bench: Team and Files left)", () => {
    const team = box("team:core", 0, 0, 420, 300);
    const files = box("files:all", 460, 0, 380, 300);
    const boq = box("deliverable:boq", 2400, 0, 900, 420);
    expect(revealed([boq], [files, team], [], area)).toBeNull();
    expect(revealed([boq], [], [], area)!.map((f) => f.key)).toEqual(["deliverable:boq"]); // nothing to keep: it goes there
  });
});
