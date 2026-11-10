import { describe, expect, it } from "vitest";
import { daysUntil, isMorning } from "./days";

describe("days left", () => {
  it("counts whole days from the screen's own day, at any hour", () => {
    expect(daysUntil("2026-11-16", new Date(2026, 10, 9, 0, 5))).toBe(7);
    expect(daysUntil("2026-11-16", new Date(2026, 10, 9, 23, 55))).toBe(7);
    expect(daysUntil("2026-11-09", new Date(2026, 10, 9, 18))).toBe(0);
    expect(daysUntil("2026-11-05", new Date(2026, 10, 9))).toBe(-4);
    expect(daysUntil("2027-01-02", new Date(2026, 11, 31))).toBe(2);
  });

  it("is morning until noon", () => {
    expect(isMorning(new Date(2026, 10, 9, 11, 59))).toBe(true);
    expect(isMorning(new Date(2026, 10, 9, 12))).toBe(false);
  });
});
