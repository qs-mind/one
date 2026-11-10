// The rules every file of the new interface keeps, as pure checks on (path, source text).
// Each returns a list of problems; rules.test.ts runs them over the files and over bad samples.

/** Folders of the new interface. Later jobs append theirs. */
export const NEW_UI_ROOTS = ["ui/src/design", "ui/src/texts", "ui/src/next"] as const;

/** Copied code: shadcn's components and CSS, as the CLI wrote them. */
export const isCopied = (path: string) => path.startsWith("ui/src/design/ui/");
const COPIED_CSS = "ui/src/design/ui/shadcn-tailwind.css";
const TOKENS = "ui/src/design/tokens.css";
const COPPER_HOME = "ui/src/design/now-waiting.tsx";

const stripComments = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");

/** The words of every string literal: where class names live in .ts and .tsx. */
function classTokens(source: string): string[] {
  const literals = [...source.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`/g)].map((m) => m[1] ?? m[2] ?? m[3] ?? "");
  return literals.flatMap((literal) => literal.split(/\s+/)).filter(Boolean);
}

/** Splits "data-[side=left]:hover:-ml-2!" into its variants and its utility ("-ml-2" without "!" or the minus). */
function splitToken(token: string): { variants: string[]; utility: string } {
  const parts: string[] = [];
  let depth = 0;
  let current = "";
  for (const char of token) {
    if (char === "[" || char === "(") depth++;
    if (char === "]" || char === ")") depth--;
    if (char === ":" && depth === 0) {
      parts.push(current);
      current = "";
    } else current += char;
  }
  const utility = current.replace(/^!|!$/g, "").replace(/^-/, "");
  return { variants: parts, utility };
}

/** Tests spell what the rules forbid, so the class and text rules (6 to 13) skip them. */
const isTest = (path: string) => /\.test\.tsx?$/.test(path);
const isScript = (path: string) => /\.tsx?$/.test(path);

/** Each class token of the file as its variants and utility; empty for CSS and tests. */
function classParts(path: string, source: string) {
  if (!isScript(path) || isTest(path)) return [];
  return classTokens(stripComments(source)).map((token) => ({ token, ...splitToken(token) }));
}

// 1. No colour outside tokens.css: no hex value, colour function or white/black class anywhere else in the new folders.
const COLOUR_FUNCTION = /\b(rgba?|hsla?|oklch|oklab|color-mix)\(/g;
const WHITE_BLACK = /^(bg|text|border|fill|stroke|outline|decoration)-(white|black)(\/|$)/;

export function hexColours(path: string, source: string): string[] {
  if (path === TOKENS || path === COPIED_CSS) return [];
  const code = stripComments(source);
  return [
    ...[...code.matchAll(/#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b/g)].map((m) => `${path}: hex colour ${m[0]}`),
    ...[...code.matchAll(COLOUR_FUNCTION)].map((m) => `${path}: colour function ${m[0]}`),
    ...classParts(path, source)
      .filter(({ utility }) => WHITE_BLACK.test(utility))
      .map(({ token }) => `${path}: colour class "${token}"`),
  ];
}

// 2. No left or right where a logical property exists.
const PHYSICAL_UTILITY =
  /^(m[lr]|p[lr]|left|right|scroll-m[lr]|scroll-p[lr])-|^(text|float|clear|origin)-(left|right)$|^border-[lr](-|$)|^rounded-([lr]|[tb][lr])(-|$)|^slide-.*-(left|right)/;
const PHYSICAL_CSS =
  /(^|[\s;{])(margin-left|margin-right|padding-left|padding-right|border-left[\w-]*|border-right[\w-]*|left|right|scroll-margin-(left|right)|scroll-padding-(left|right))\s*:|(text-align|float|clear)\s*:\s*(left|right)\b/gm;
const PHYSICAL_INLINE = /\b(marginLeft|marginRight|paddingLeft|paddingRight|left|right)\s*:|textAlign\s*:\s*["'](left|right)["']|\bside=["'](left|right)["']/g;

export function physicalSides(path: string, source: string): string[] {
  if (path === COPIED_CSS) return [];
  const code = stripComments(source);
  if (path.endsWith(".css"))
    return [...code.matchAll(PHYSICAL_CSS)].map((m) => `${path}: physical property "${m[0].trim()}"`);
  const problems: string[] = [];
  for (const token of classTokens(code)) {
    const { variants, utility } = splitToken(token);
    // In copied files a class under data-[side=left|right] is dead while only logical sides are passed.
    if (isCopied(path) && variants.some((v) => /data-\[side=(left|right)\]/.test(v))) continue;
    if (PHYSICAL_UTILITY.test(utility)) problems.push(`${path}: physical class "${token}"`);
  }
  if (!isCopied(path)) {
    for (const m of code.matchAll(PHYSICAL_INLINE)) problems.push(`${path}: physical "${m[0]}"`);
    for (const literal of code.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`/g)) {
      const words = (literal[1] ?? literal[2] ?? literal[3] ?? "").split(/\s+/);
      const moves = words.some((w) => /^-?translate-x-/.test(splitToken(w).utility) && !w.includes("rtl:"));
      const twin = words.some((w) => w.startsWith("rtl:") && /translate-x-/.test(w));
      if (moves && !twin) problems.push(`${path}: translate-x without an rtl: twin in "${literal[0]}"`);
    }
  }
  return problems;
}

// 3. No import from the old interface: packages, @/design, @/texts, @/next, or a relative path inside its own root.
const IMPORT = /(?:^|[^\w$.])(?:import|export)\s[^"'`;]*?from\s*["']([^"']+)["']|(?:^|[^\w$.])import\s*\(?\s*["']([^"']+)["']|@import\s+(?:url\()?["']([^"']+)["']/gm;
const OWN_ALIASES = ["@/design/", "@/texts/", "@/next/"];

function normalise(path: string): string {
  const out: string[] = [];
  for (const part of path.split("/")) {
    if (part === "..") out.pop();
    else if (part !== "." && part !== "") out.push(part);
  }
  return out.join("/");
}

export function oldImports(path: string, source: string): string[] {
  const root = NEW_UI_ROOTS.find((r) => path.startsWith(`${r}/`));
  const problems: string[] = [];
  for (const m of stripComments(source).matchAll(IMPORT)) {
    const spec = m[1] ?? m[2] ?? m[3] ?? "";
    const where = `${path}: import "${spec}"`;
    if (spec.endsWith(".css") && !path.endsWith(".css") && spec !== "@/design/tokens.css") problems.push(`${where} (only tokens.css)`);
    if (spec.startsWith(".")) {
      const target = normalise(`${path.slice(0, path.lastIndexOf("/"))}/${spec}`);
      if (!root || !target.startsWith(`${root}/`)) problems.push(`${where} leaves its folder`);
    } else if (spec.startsWith("@/")) {
      if (!OWN_ALIASES.some((a) => spec.startsWith(a))) problems.push(`${where} is the old interface`);
    } else if (spec.startsWith("/") || spec.startsWith("ui/")) problems.push(`${where} is a path`);
  }
  return problems;
}

// 4. Copper only through now/waiting: their classes and variables live in now-waiting.tsx alone
//    (tokens.css is checked by tokens.test.ts: --copper feeds --now only).
const COPPER_CLASS = /^(bg|text|border|fill|stroke|outline|decoration|ring|caret|accent|from|via|to|shadow|divide|placeholder)-(now|waiting|copper)(\/|$)/;
const COPPER_VAR = /var\(--(now|waiting|copper)\)|--color-(now|waiting|copper)\b/g;

export function copperOutside(path: string, source: string): string[] {
  if (path === TOKENS || path === COPPER_HOME) return [];
  const code = stripComments(source);
  const problems = [...code.matchAll(COPPER_VAR)].map((m) => `${path}: ${m[0]}`);
  if (!path.endsWith(".css"))
    for (const token of classTokens(code))
      if (COPPER_CLASS.test(splitToken(token).utility)) problems.push(`${path}: copper class "${token}"`);
  return problems;
}

// 5. No file over 300 lines, except the copied shadcn CSS.
export function tooLong(path: string, source: string): string[] {
  const lines = source.split("\n").length - (source.endsWith("\n") ? 1 : 0);
  return path !== COPIED_CSS && lines > 300 ? [`${path}: ${lines} lines`] : [];
}

// 6. Nothing in web storage.
export function webStorage(path: string, source: string): string[] {
  if (isTest(path)) return [];
  return [...stripComments(source).matchAll(/\b(localStorage|sessionStorage|indexedDB|document\.cookie)\b/g)].map(
    (m) => `${path}: ${m[0]}`,
  );
}

// 7. No shadow, gradient, blur, loop or slow state change.
const STILL_OWN =
  /^(shadow-(?!none$)|inset-shadow-|drop-shadow|bg-gradient-|bg-linear-|bg-radial|bg-conic|from-|via-|to-|blur|backdrop-|animate-|shimmer|scroll-fade)/;
const GENERATED = /^(shadow-|animate-(in|out|none)$)/; // copied: compile to nothing (no shadow tokens, no tw-animate-css)
const STILL_CSS = /(linear|radial|conic)-gradient\(|box-shadow\s*:(?!\s*none\b)[^;]+|filter\s*:[^;]*blur\(/g;

export function motionAndDepth(path: string, source: string): string[] {
  const problems = path.endsWith(".css") && path !== COPIED_CSS
    ? [...stripComments(source).matchAll(STILL_CSS)].map((m) => `${path}: "${m[0].trim()}"`)
    : [];
  for (const { token, utility } of classParts(path, source)) {
    if (STILL_OWN.test(utility) && !(isCopied(path) && GENERATED.test(utility))) problems.push(`${path}: "${token}"`);
    if (/^duration-/.test(utility) && utility !== "duration-240") problems.push(`${path}: "${token}" (only duration-240)`);
  }
  return problems;
}

// 8. Type: no tight leading, capitals or slant anywhere; own files keep the scale's keys and the two weights.
const TYPE_ALL = /^(leading-none|leading-\[.*\]|uppercase|italic)$/;
const TYPE_OWN = /^(text-sm|font-(thin|extralight|light|medium|semibold|extrabold|black|\[.*\])|tracking-.*)$/;
const WORDMARK = "ui/src/design/Wordmark.tsx";

export function typeRules(path: string, source: string): string[] {
  const problems: string[] = [];
  for (const { token, utility } of classParts(path, source)) {
    if (TYPE_ALL.test(utility)) problems.push(`${path}: "${token}"`);
    else if (!isCopied(path) && TYPE_OWN.test(utility)) {
      if (path === WORDMARK && (utility === "font-[600]" || utility === "tracking-[1px]")) continue;
      problems.push(`${path}: "${token}" in an own file`);
    }
  }
  return problems;
}

// 9. No opacity for disabled, no dark: (the tokens carry dark).
export function disabledAndDark(path: string, source: string): string[] {
  return classParts(path, source)
    .filter(({ token, variants }) => /(^|:)[^:\s]*disabled[^:\s]*:(.*:)?opacity-/.test(token) || variants.includes("dark"))
    .map(({ token }) => `${path}: "${token}"`);
}

// 10. `num` stands alone: no logical margin, padding or inset in the same class string (2.3).
export function numAlone(path: string, source: string): string[] {
  if (!isScript(path) || isTest(path)) return [];
  const problems: string[] = [];
  for (const m of stripComments(source).matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`/g)) {
    const utilities = (m[1] ?? m[2] ?? m[3] ?? "").split(/\s+/).map((w) => splitToken(w).utility);
    if (utilities.includes("num") && utilities.some((u) => /^(ms|me|ps|pe|start|end)-/.test(u)))
      problems.push(`${path}: num with a logical offset in "${m[0]}"`);
  }
  return problems;
}

// 12. No class for a token that does not exist.
const MISSING_TOKEN = /^(bg|text|border|ring|outline|fill|stroke)-(destructive|secondary|sidebar|chart|waiting-surface)/;

export function missingTokens(path: string, source: string): string[] {
  return classParts(path, source)
    .filter(({ utility }) => MISSING_TOKEN.test(utility))
    .map(({ token }) => `${path}: "${token}"`);
}

// 13. No dir="auto": it follows the first strong letter, and "Lead QS طلّع…" would turn left to right.
export function dirAuto(path: string, source: string): string[] {
  if (isTest(path)) return [];
  return [...stripComments(source).matchAll(/dir(=|\s*:\s*)["']auto["']/g)].map((m) => `${path}: ${m[0]}`);
}

export const RULES = {
  hexColours,
  physicalSides,
  oldImports,
  copperOutside,
  tooLong,
  webStorage,
  motionAndDepth,
  typeRules,
  disabledAndDark,
  numAlone,
  missingTokens,
  dirAuto,
} as const;
