import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { stateDot, type StageState } from "@/design/now-waiting";
import { StatusDot } from "@/design/StatusDot";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("StatusDot (%s)", (dir) => {
  it.each(["done", "now", "waiting", "pending"] satisfies StageState[])("the %s dot is hidden, still, and has its state's look", (state) => {
    renderIn(dir, <StatusDot state={state} />);
    const dot = document.querySelector<HTMLElement>("[data-state-fill]");
    expect(dot?.getAttribute("aria-hidden")).toBe("true");
    expect(dot?.getAttribute("data-state-fill")).toBe(state);
    expect(dot?.className).toContain(stateDot[state]);
    expect(dot?.className).toMatch(/\bsize-2\.5\b/);
    expect(dot?.className).not.toMatch(/animate-/);
  });
});
