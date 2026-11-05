// ONE's own controls, all native underneath: the brand focus ring on every one, never the engine's `auto 1px`
// outline; checkboxes, radios and selects in Ink, Paper and Slate, the select's chevron at its inline end; a disabled
// button in Slate on Stone, never a grey wash.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "../styles.css"), "utf8");
const rule = (selector: string) => {
  const at = css.indexOf(`${selector} {`);
  return at < 0 ? "" : css.slice(at, css.indexOf("}", at) + 1);
};

describe("brand controls", () => {
  it("every control that takes focus shows a 2 px Ink ring, as a base rule a control's own classes can refine", () => {
    const ring = rule(":focus-visible");
    expect(ring).toMatch(/outline:\s*2px solid var\(--color-ink\)/);
    expect(ring).toMatch(/outline-offset:\s*2px/);
    expect(css.slice(0, css.indexOf(":focus-visible {"))).toMatch(/@layer base \{\s*$/);
    expect(css).not.toMatch(/outline:\s*auto/);
  });

  it("checkboxes and radios are ticked in Ink at 16 px", () => {
    const box = rule('input[type="radio"]');
    expect(box).toMatch(/accent-color:\s*var\(--color-ink\)/);
    expect(box).toMatch(/width:\s*1rem/);
  });

  it("a select is Paper with a Slate edge and a Slate chevron at its inline end, the left in Arabic", () => {
    const select = rule("  select");
    expect(select).toMatch(/appearance:\s*none/);
    expect(select).toMatch(/background-color:\s*var\(--color-paper\)/);
    expect(select).toMatch(/rgb\(110 106 100 \/ 0\.4\)/);
    expect(select).toMatch(/stroke='%236e6a64'/); // the chevron in Slate
    expect(select).toMatch(/background-position:\s*right/);
    expect(rule('[dir="rtl"] select:not([dir="ltr"]),\n  select[dir="rtl"]')).toMatch(/background-position:\s*left/);
    expect(rule('\nselect:not([class*="pe-"])')).toMatch(/padding-inline-end:\s*2\.25rem/); // room for the chevron
    expect(select).toMatch(/max-width:\s*100%/); // a long option never pushes its panel sideways
  });

  it("a disabled button keeps the brand: Slate words, full opacity, a filled one on Stone", () => {
    const off = rule("button:disabled");
    expect(off).toMatch(/opacity:\s*1/);
    expect(off).toMatch(/color:\s*var\(--color-slate\)/);
    expect(rule("button:disabled:is(.bg-ink, .bg-copper, [class*=\"bg-ink/\"])")).toMatch(/background-color:\s*var\(--color-stone\)/);
  });
});
