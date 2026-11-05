// Focus rings show for the keyboard only: after a click or a touch the page is marked, and styles.css hides the ring
// (outline) until a key moves focus again. Text fields keep their focus look: a click is how they are typed into.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent } from "@testing-library/react";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { installPointerFocus } from "./pointerFocus";

const css = readFileSync(join(__dirname, "../styles.css"), "utf8");

const marked = () => document.documentElement.hasAttribute("data-pointer");
let remove: () => void;
beforeAll(() => (remove = installPointerFocus()));
afterAll(() => remove());

describe("focus rings after a click", () => {
  it("a press with the mouse marks the page; a key that moves focus clears it", () => {
    fireEvent.pointerDown(document.body);
    expect(marked()).toBe(true);
    fireEvent.keyDown(document.body, { key: "Tab" });
    expect(marked()).toBe(false);
    fireEvent.pointerDown(document.body);
    fireEvent.keyDown(document.body, { key: "ArrowDown" });
    expect(marked()).toBe(false);
  });

  it("typing, a modifier or Escape is not moving focus: the mark stays", () => {
    fireEvent.pointerDown(document.body);
    for (const key of ["a", "Shift", "Control", "Meta", "Escape", "Enter"]) fireEvent.keyDown(document.body, { key });
    expect(marked()).toBe(true);
  });

  it("styles.css hides the ring while marked, but not a text field's", () => {
    const rule = css.match(/html\[data-pointer\][^{]*:focus-visible[^{]*\{[^}]*\}/)?.[0] ?? "";
    expect(rule).toMatch(/outline:\s*none/);
    expect(rule).toMatch(/:not\(input, textarea, select, \[contenteditable/);
  });
});
