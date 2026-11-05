// The first step's language choice wipes the page in from the chosen button (docs/specs/2026-11-05-motion-design.md 2.7).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { language, setLanguage, texts } from "../i18n";
import { Language } from "./Language";

const animate = vi.fn(() => ({ finished: Promise.resolve(), finish() {} }));

beforeEach(() => {
  setLanguage("ar");
  Element.prototype.animate = animate as unknown as Element["animate"];
});

afterEach(() => {
  delete (Element.prototype as { animate?: unknown }).animate;
  delete (document as { startViewTransition?: unknown }).startViewTransition;
});

it("choosing English wipes it in from the English button's centre", async () => {
  const start = vi.fn((update: () => void) => {
    update();
    return { ready: Promise.resolve(), finished: Promise.resolve(), skipTransition() {} };
  });
  Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
  const user = userEvent.setup();
  render(<Language nav={{ pass: async () => true }} />);
  const english = screen.getByRole("button", { name: texts.languageEnglish.en });
  english.getBoundingClientRect = () => new DOMRect(400, 300, 200, 80);
  await user.click(english);
  expect(start).toHaveBeenCalledTimes(1);
  expect(language()).toBe("en");
  await vi.waitFor(() =>
    expect(animate).toHaveBeenCalledWith(
      { clipPath: [expect.stringContaining("at 500px 340px"), expect.stringContaining("at 500px 340px")] },
      expect.anything(),
    ),
  );
});

it("choosing the language already shown does nothing", async () => {
  const start = vi.fn();
  Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
  const user = userEvent.setup();
  render(<Language nav={{ pass: async () => true }} />);
  await user.click(screen.getByRole("button", { name: texts.languageArabic.ar }));
  expect(start).not.toHaveBeenCalled();
});
