// Every colour token of tokens.css with its light and dark definition, as code (section 1.2 of the specification).
// The swatch reads the token itself; the value shown under it is computed in the page, so nothing here is a colour.
export type TokenRow = { name: string; inLight: string; inDark: string };

export const TOKENS: readonly TokenRow[] = [
  { name: "background", inLight: "paper", inDark: "ink" },
  { name: "foreground", inLight: "ink", inDark: "paper" },
  { name: "card", inLight: "paper", inDark: "stone 4% in ink" },
  { name: "popover", inLight: "card", inDark: "card" },
  { name: "muted", inLight: "stone", inDark: "stone 8% in ink" },
  { name: "muted-hover", inLight: "ink 5% in muted", inDark: "paper 7% in muted" },
  { name: "muted-foreground", inLight: "slate", inDark: "slate 60% in paper" },
  { name: "primary", inLight: "ink", inDark: "paper" },
  { name: "primary-foreground", inLight: "paper", inDark: "ink" },
  { name: "primary-hover", inLight: "ink 88% in paper", inDark: "paper 88% in ink" },
  { name: "primary-pressed", inLight: "ink 78% in paper", inDark: "paper 78% in ink" },
  { name: "accent", inLight: "ink at 5%", inDark: "paper at 7%" },
  { name: "pressed", inLight: "ink at 10%", inDark: "paper at 12%" },
  { name: "border", inLight: "slate 10% in stone", inDark: "stone 13% in ink" },
  { name: "line", inLight: "slate 21% in stone", inDark: "stone 22% in ink" },
  { name: "input", inLight: "line", inDark: "line" },
  { name: "row-line", inLight: "slate 5% in stone", inDark: "stone 9% in ink" },
  { name: "ring", inLight: "foreground", inDark: "foreground" },
  { name: "now", inLight: "copper", inDark: "copper 60% in paper" },
  { name: "waiting", inLight: "now", inDark: "now" },
  { name: "selection", inLight: "ink at 14%", inDark: "paper at 20%" },
  { name: "scrim", inLight: "ink at 45%", inDark: "ink at 70%" },
  { name: "disabled", inLight: "border", inDark: "border" },
  { name: "hold-fill", inLight: "primary-foreground at 30%", inDark: "primary-foreground at 30%" },
];

const hex2 = (n: number) => Math.round(Math.min(255, Math.max(0, n))).toString(16).padStart(2, "0").toUpperCase();

/** A computed colour (as the browser gives it, in 0–255 or, from Chromium, in sRGB 0–1) as six hex digits, plus its alpha. */
export function describeColour(computed: string): string {
  const numbers = (computed.match(/-?[\d.]+/g) ?? []).map(Number);
  const unit = computed.includes("srgb") ? 255 : 1;
  const [r = 0, g = 0, b = 0, a = 1] = numbers;
  const value = `#${hex2(r * unit)}${hex2(g * unit)}${hex2(b * unit)}`;
  return a < 1 ? `${value} · ${Math.round(a * 100)}%` : value;
}
