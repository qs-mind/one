// ONE's scrollbars are thin and quiet: Slate at low opacity, the thumb thicker and darker only under the pointer.
// The standard properties for an engine that has them; ::-webkit-scrollbar for WebKitGTK, WKWebView and WebView2.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "../styles.css"), "utf8");

const SLATE = /rgb\(110 106 100 \/ 0\.(\d+)\)/;
const rule = (selector: string) => {
  const at = css.indexOf(`${selector} {`);
  return at < 0 ? "" : css.slice(at, css.indexOf("}", at) + 1);
};

describe("scrollbars", () => {
  it("are thin, in Slate at low opacity, for the engines with the standard properties", () => {
    expect(css).toMatch(/scrollbar-width:\s*thin/);
    const color = css.match(/scrollbar-color:\s*([^;]+);/)?.[1] ?? "";
    expect(color).toMatch(SLATE);
    expect(Number(`0.${color.match(SLATE)![1]}`)).toBeLessThanOrEqual(0.4);
  });

  it("have a WebKit fallback: a narrow Slate thumb on a clear track, thicker and darker on hover", () => {
    const thumb = rule("::-webkit-scrollbar-thumb");
    const hover = rule("::-webkit-scrollbar-thumb:hover");
    expect(rule("::-webkit-scrollbar")).toMatch(/width:\s*\d+px/);
    expect(thumb).toMatch(SLATE);
    expect(thumb).toMatch(/background-clip:\s*content-box/);
    const border = (r: string) => Number(r.match(/border(?:-width)?:\s*(\d+)px/)?.[1]);
    expect(border(hover)).toBeLessThan(border(thumb)); // a thinner clear border: a thicker thumb
    const alpha = (r: string) => Number(`0.${r.match(SLATE)![1]}`);
    expect(alpha(hover)).toBeGreaterThan(alpha(thumb));
    expect(rule("::-webkit-scrollbar-track")).toMatch(/transparent/);
  });
});
