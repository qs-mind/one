import { describe, expect, it } from "vitest";
import { GRID_SIZE } from "./test-setup";

describe("test setup", () => {
  it("gives grid containers a size and a ResizeObserver, and leaves other elements at 0", () => {
    const grid = document.createElement("div");
    grid.setAttribute("role", "grid");
    const other = document.createElement("div");
    expect([grid.clientWidth, grid.clientHeight]).toEqual([GRID_SIZE.width, GRID_SIZE.height]);
    expect([other.clientWidth, other.clientHeight]).toEqual([0, 0]);
    const observer = new ResizeObserver(() => {});
    observer.observe(grid);
    observer.disconnect();
  });
});
