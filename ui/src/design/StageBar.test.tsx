import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { stateFill, type StageState } from "@/design/now-waiting";
import { StageBar } from "@/design/StageBar";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

const STAGES: { state: StageState; weight: number }[] = [
  { state: "done", weight: 1 },
  { state: "now", weight: 1 },
  { state: "waiting", weight: 2 },
  { state: "pending", weight: 3 },
];

describe.each(DIRS)("StageBar (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const label = text(surfaces.stageLabel, lang, { step: 2, total: 4, name: text(surfaces.stageQueries, lang) });

  it("is one image named in words, passive", () => {
    renderIn(dir, <StageBar stages={STAGES} label={label} />);
    const bar = screen.getByRole("img", { name: label });
    expect(bar.hasAttribute("tabindex")).toBe(false);
    expect(bar.children).toHaveLength(STAGES.length);
  });

  it("draws one segment per stage, sized by its weight, filled by its state", () => {
    renderIn(dir, <StageBar stages={STAGES} label={label} />);
    const segments = [...screen.getByRole("img").children] as HTMLElement[];
    segments.forEach((segment, i) => {
      const stage = STAGES[i]!;
      expect(segment.getAttribute("data-state-fill")).toBe(stage.state);
      expect(segment.className).toContain(stateFill[stage.state]);
      expect(segment.className).toMatch(/\bh-1\.5\b/);
      expect(segment.className).toMatch(/duration-240 ease-linear/);
      expect(segment.style.flex).toMatch(new RegExp(`^${stage.weight} 1 0%`));
    });
  });

  it("a stage without a weight counts as 1", () => {
    renderIn(dir, <StageBar stages={[{ state: "done" }, { state: "pending" }]} label={label} />);
    const [first] = [...screen.getByRole("img").children] as HTMLElement[];
    expect(first?.style.flex).toMatch(/^1 1 0%/);
  });
});
