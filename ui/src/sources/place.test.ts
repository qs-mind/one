import { describe, expect, it } from "vitest";
import { CARD_EDGE, CARD_GAP, placeCard } from "./place";

const view = { width: 1440, height: 900 };
const card = { width: 320, height: 300 };
const at = (left: number, top: number, w = 80, h = 20) => ({ left, top, right: left + w, bottom: top + h });

describe("a source card's place on the screen", () => {
  it("stands under its number, on the number's start edge (the right in Arabic)", () => {
    expect(placeCard(at(600, 200), card, view, false)).toMatchObject({ top: 220 + CARD_GAP, left: 600 });
    expect(placeCard(at(600, 200), card, view, true)).toMatchObject({ top: 220 + CARD_GAP, left: 680 - 320 });
  });

  it("flips above a number near the window's foot, whole, never under the composer", () => {
    const placed = placeCard(at(600, 800), card, view, true);
    expect(placed.top).toBe(800 - CARD_GAP - 300);
    expect(placed.top + 300).toBeLessThanOrEqual(view.height - CARD_EDGE);
  });

  it("shifts along to stay on screen: a number at the window's start edge, or past it", () => {
    expect(placeCard(at(-40, 200), card, view, false).left).toBe(CARD_EDGE);
    expect(placeCard(at(40, 200), card, view, true).left).toBe(CARD_EDGE); // its right edge would be at 120
    expect(placeCard(at(1400, 200), card, view, false).left).toBe(view.width - CARD_EDGE - 320);
  });

  it("is never taller than the room it has, so its last line can always be scrolled to", () => {
    const small = { width: 1000, height: 400 };
    const placed = placeCard(at(300, 180), { width: 320, height: 600 }, small, false);
    expect(placed.maxHeight).toBeLessThanOrEqual(small.height - 2 * CARD_EDGE);
    expect(placed.top).toBeGreaterThanOrEqual(CARD_EDGE);
    expect(placed.top + Math.min(600, placed.maxHeight)).toBeLessThanOrEqual(small.height - CARD_EDGE);
  });
});
