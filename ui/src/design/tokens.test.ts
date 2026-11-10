// @vitest-environment node
// Reads tokens.css and base.css as text (jsdom resolves neither var() nor color-mix()) and checks the colour rules
// and the contrast of every text and ground pair, in both themes. Port of the spec's tokens-check.mjs.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const strip = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");
const tokens = strip(readFileSync(new URL("./tokens.css", import.meta.url), "utf8"));
const base = strip(readFileSync(new URL("./base.css", import.meta.url), "utf8"));

function block(css: string, start: RegExp): string {
  const m = start.exec(css);
  if (!m) throw new Error(`block not found: ${start}`);
  let depth = 1;
  let j = m.index + m[0].length;
  while (depth) {
    const c = css[j++];
    if (c === undefined) throw new Error(`unclosed block: ${start}`);
    if (c === "{") depth++;
    else if (c === "}") depth--;
  }
  return css.slice(m.index + m[0].length, j - 1);
}
const decls = (body: string): Record<string, string> =>
  Object.fromEntries([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]));

const light = decls(block(tokens, /:root\s*\{/));
const dark = { ...light, ...decls(block(tokens, /@utility theme-dark\s*\{/)) };

type Rgba = [number, number, number, number];
const FIVE = ["#0e0f12", "#f2eee7", "#f9f8f4", "#6e6a64", "#a6491b"];

function resolve(value: string, theme: Record<string, string>, seen: string[] = []): Rgba {
  const v = value.trim();
  if (/^#[0-9a-f]{6}$/i.test(v)) return [1, 3, 5].map((i) => parseInt(v.slice(i, i + 2), 16)).concat(1) as Rgba;
  if (v === "transparent") return [0, 0, 0, 0];
  let m = /^var\((--[\w-]+)\)$/.exec(v);
  if (m) {
    const name = m[1]!;
    if (seen.includes(name) || !(name in theme)) throw new Error(`bad var ${name}`);
    return resolve(theme[name]!, theme, [...seen, name]);
  }
  m = /^color-mix\(in srgb,\s*(.+?)\s+([\d.]+)%,\s*(.+)\)$/.exec(v);
  if (m) {
    const a = resolve(m[1]!, theme, seen);
    const p = Number(m[2]) / 100;
    const b = resolve(m[3]!, theme, seen);
    if (b[3] === 0) return [a[0], a[1], a[2], a[3] * p]; // a at p% in transparent = a with alpha p
    return [0, 1, 2].map((i) => a[i]! * p + b[i]! * (1 - p)).concat(1) as Rgba;
  }
  throw new Error(`not an allowed colour form: ${v}`);
}
const over = (fg: Rgba, bg: Rgba): Rgba => [0, 1, 2].map((i) => fg[i]! * fg[3] + bg[i]! * (1 - fg[3])).concat(1) as Rgba;
const lin = (x: number) => {
  const c = Math.round(x) / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
const lum = (c: Rgba) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
const ratio = (a: Rgba, b: Rgba) => {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m) as [number, number];
  return (x + 0.05) / (y + 0.05);
};

// Text on a ground reaches 4.5; "a+b" is overlay b laid on a.
const TEXT_PAIRS: [string, string[]][] = [
  ["foreground", ["background", "card", "muted", "muted-hover", "background+accent", "card+accent", "background+pressed", "card+pressed", "background+selection", "muted+selection", "disabled"]],
  ["muted-foreground", ["background", "card", "muted", "background+accent", "card+accent"]],
  ["now", ["background", "card", "muted", "muted-hover", "background+accent", "card+accent"]],
  ["primary-foreground", ["primary", "primary-hover", "primary-pressed", "primary+hold-fill", "primary-hover+hold-fill"]],
  ["background", ["foreground"]], // the tooltip
];
// Edges and fills that carry meaning reach 3.0.
const EDGE_PAIRS: [string, string[]][] = [
  ["ring", ["background", "card", "muted", "muted-hover"]],
  ["muted-foreground", ["background", "card", "muted"]],
  ["now", ["background", "card", "muted", "line"]],
  ["foreground", ["line"]],
];

describe("tokens.css", () => {
  it("names exactly the five colours, and base.css none", () => {
    const hexes = [...tokens.matchAll(/#[0-9a-f]{3,8}\b/gi)].map((m) => m[0].toLowerCase());
    expect(hexes.sort()).toEqual([...FIVE].sort());
    expect(base).not.toMatch(/#[0-9a-f]{3,8}\b/i);
  });

  it("writes every other colour as var() or color-mix(in srgb, …), resolving in both themes", () => {
    for (const theme of [light, dark])
      for (const [name, value] of Object.entries(theme)) {
        if (/^(--radius|--rail-w|--side-w|--measure|--gutter|--sheet-|--font-)/.test(name)) continue;
        expect(() => resolve(value, theme), `${name}: ${value}`).not.toThrow();
      }
    expect(tokens).not.toMatch(/\b(rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\(/);
    expect(tokens).not.toMatch(/color-mix\(in (?!srgb)/);
  });

  it.each([
    ["light", light],
    ["dark", dark],
  ] as const)("reaches the contrast of every pair in %s", (_name, theme) => {
    const col = (k: string) => resolve(`var(--${k})`, theme);
    const ground = (g: string) => g.split("+").map(col).reduce((bg, layer) => over(layer, bg));
    const failures: string[] = [];
    for (const [min, pairs] of [[4.5, TEXT_PAIRS], [3, EDGE_PAIRS]] as const)
      for (const [fg, grounds] of pairs)
        for (const g of grounds) {
          const r = ratio(col(fg), ground(g));
          if (r < min) failures.push(`${fg} on ${g}: ${r.toFixed(2)} < ${min}`);
        }
    expect(failures).toEqual([]);
  });

  it("lets copper reach the page only through --now and --waiting", () => {
    const users = (name: string) => [...tokens.matchAll(new RegExp(`(--[\\w-]+)\\s*:[^;]*var\\(--${name}\\)`, "g"))].map((m) => m[1]);
    expect(users("copper")).toEqual(["--now", "--now"]);
    expect(users("now").sort()).toEqual(["--color-now", "--waiting"]);
    expect(users("waiting")).toEqual(["--color-waiting"]);
  });

  it("applies the dark values under exactly the two conditions", () => {
    expect(tokens.match(/@apply theme-dark;/g)).toHaveLength(2);
    expect(tokens).toMatch(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{\s*@apply theme-dark;/);
    expect(tokens).toMatch(/:root\[data-theme="dark"\]\s*\{\s*@apply theme-dark;/);
  });

  it("removes Tailwind's own scales and keeps lines at 1.5 or more, weights at 400 and 700", () => {
    const theme = block(tokens, /@theme\s*\{/);
    for (const reset of ["color", "text", "font-weight", "tracking", "leading", "shadow", "animate"])
      expect(theme).toContain(`--${reset}-*: initial;`);
    const values = decls(theme);
    for (const [name, value] of Object.entries(values)) {
      if (/^--text-.*--line-height$|^--leading-/.test(name)) expect(Number(value), name).toBeGreaterThanOrEqual(1.5);
      if (name.startsWith("--font-weight-")) expect(["400", "700"], name).toContain(value);
    }
  });

  it("declares no token for a role the system does not have", () => {
    expect(tokens).not.toMatch(/--(secondary|destructive|sidebar|chart-|waiting-surface)/);
  });
});
