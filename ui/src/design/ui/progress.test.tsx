import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Progress, ProgressLabel, ProgressValue } from "@/design/ui/progress";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Progress (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const words = text(surfaces.downloaded, lang, { done: 62, total: 135 });

  it("carries the real value and the caller's words for assistive technology", () => {
    renderIn(
      dir,
      <Progress value={46} aria-valuetext={words}>
        <ProgressLabel>{text(surfaces.progressLabel, lang)}</ProgressLabel>
        <ProgressValue>{() => words}</ProgressValue>
      </Progress>,
    );
    const bar = screen.getByRole("progressbar", { name: text(surfaces.progressLabel, lang) });
    expect(bar.getAttribute("aria-valuenow")).toBe("46");
    expect(bar.getAttribute("aria-valuetext")).toBe(words);
    expect(bar.hasAttribute("tabindex")).toBe(false); // passive: not a Tab stop
    const value = document.querySelector('[data-slot="progress-value"]');
    expect(value?.textContent).toBe(words);
    expect(value?.className).not.toMatch(/\bnum\b/);
    expect(value?.className).toMatch(/\bms-auto\b/);
  });

  it("draws a 6px track in --border, a --primary fill that moves only at 240ms linear", () => {
    renderIn(dir, <Progress value={46} aria-label={text(surfaces.progressLabel, lang)} />);
    const track = document.querySelector('[data-slot="progress-track"]');
    const fill = document.querySelector<HTMLElement>('[data-slot="progress-indicator"]');
    expect(track?.className).toMatch(/\bh-1\.5\b/);
    expect(track?.className).toMatch(/\bbg-border\b/);
    expect(fill?.className).toMatch(/\bbg-primary\b/);
    expect(fill?.className).toMatch(/duration-240 ease-linear/);
    expect(fill?.className).not.toMatch(/transition-all/);
    expect(fill?.style.width).toBe("46%");
  });

  it("with no value there is no moving bar: the fill has no width and the label says what waits", () => {
    renderIn(
      dir,
      <Progress value={null}>
        <ProgressLabel>{text(surfaces.progressWaiting, lang)}</ProgressLabel>
      </Progress>,
    );
    const bar = screen.getByRole("progressbar", { name: text(surfaces.progressWaiting, lang) });
    expect(bar.hasAttribute("aria-valuenow")).toBe(false);
    const fill = document.querySelector<HTMLElement>('[data-slot="progress-indicator"]');
    expect(fill?.style.width ?? "").toBe("");
    expect(fill?.className ?? "").not.toMatch(/animate-/);
  });
});
