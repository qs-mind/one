// The frame every first-launch step shares: the step's content, its feedback line, then Back, Skip and Next in a bar
// that stays at the foot of the window (where it sits is checked in the bench walk, on a real layout).
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { setLanguage, texts } from "../i18n";
import { StepScreen } from "./parts";

const nav = { back: () => {}, pass: async () => true };

beforeEach(() => setLanguage("en"));

describe("StepScreen", () => {
  it("keeps Back, Skip and Next together in the step's bar, at its foot", () => {
    render(
      <StepScreen title="Connect AI" nav={nav} next={<button type="button">{texts.setupNext.en}</button>}>
        <p>content</p>
      </StepScreen>,
    );
    const bar = document.querySelector<HTMLElement>("[data-step-bar]")!;
    expect(bar).not.toBeNull();
    for (const name of [texts.setupBack.en, texts.setupSkip.en, texts.setupNext.en])
      expect(within(bar).getByRole("button", { name })).toBeInTheDocument();
    expect(bar.className).toMatch(/\bsticky\b/);
    expect(bar.className).toMatch(/\bbottom-0\b/);
    expect(bar.parentElement!.lastElementChild).toBe(bar);
  });

  it("the step's feedback line sits above the bar, never in it", () => {
    render(
      <StepScreen title="Connect AI" nav={nav} failed="The key was refused.">
        <p>content</p>
      </StepScreen>,
    );
    const line = screen.getByRole("alert");
    const bar = document.querySelector("[data-step-bar]")!;
    expect(bar.contains(line)).toBe(false);
    expect(line.compareDocumentPosition(bar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("says in the step when the core did not save it", () => {
    render(
      <StepScreen title="Language" nav={{ ...nav, notSaved: true }}>
        <p>content</p>
      </StepScreen>,
    );
    const line = screen.getByRole("alert");
    expect(line).toHaveTextContent(texts.setupNotSaved.en);
    expect(document.querySelector("[data-step-bar]")!.contains(line)).toBe(false);
  });
});
