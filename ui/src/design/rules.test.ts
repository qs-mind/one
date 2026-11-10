// @vitest-environment node
// Reads the new interface's source as text and fails on any break of the rules in test/rules.ts.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  copperOutside,
  dirAuto,
  disabledAndDark,
  hexColours,
  missingTokens,
  motionAndDepth,
  NEW_UI_ROOTS,
  numAlone,
  oldImports,
  physicalSides,
  RULES,
  tooLong,
  typeRules,
  webStorage,
} from "./test/rules";

const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const read = (path: string) => readFileSync(`${REPO}${path}`, "utf8");

function walk(dir: string): string[] {
  return readdirSync(`${REPO}${dir}`).flatMap((name) => {
    const path = `${dir}/${name}`;
    if (statSync(`${REPO}${path}`).isDirectory()) return walk(path);
    return /\.(ts|tsx|css)$/.test(name) ? [path] : [];
  });
}

// The checks themselves spell what they look for (bad samples; the five hex values of tokens.test.ts).
const SELF = ["ui/src/design/rules.test.ts", "ui/src/design/test/rules.ts", "ui/src/design/tokens.test.ts"];
const files = NEW_UI_ROOTS.flatMap(walk)
  .filter((path) => !SELF.includes(path))
  .map((path) => ({ path, source: read(path) }));

describe("rules of the new interface", () => {
  it("reads the new folders", () => {
    expect(files.map((f) => f.path)).toEqual(expect.arrayContaining(["ui/src/design/tokens.css", "ui/src/texts/common.ts"]));
  });

  it.each(Object.entries(RULES))("%s: no file breaks it", (_name, rule) => {
    expect(files.flatMap(({ path, source }) => rule(path, source))).toEqual([]);
  });

  it("keeps the dev entry out of the production build", () => {
    expect(read("vite.config.ts")).not.toMatch(/rollupOptions\s*:\s*\{[^}]*input|rolldownOptions\s*:\s*\{[^}]*input/);
    expect(read("ui/index.html")).not.toMatch(/next/);
  });
});

// Each rule must catch what it is there for.
describe("the rules catch", () => {
  const own = "ui/src/design/Thing.tsx";
  const copied = "ui/src/design/ui/thing.tsx";

  it("a hex colour outside tokens.css", () => {
    expect(hexColours(own, `<div style={{ color: "#a6491b" }} />`)).toHaveLength(1);
    expect(hexColours("ui/src/design/base.css", "a { color: #fff; }")).toHaveLength(1);
    expect(hexColours("ui/src/design/tokens.css", "--ink: #0e0f12;")).toEqual([]);
    expect(hexColours(own, `document.getElementById("root")`)).toEqual([]);
    for (const sample of ["rgb(0 0 0)", "rgba(0,0,0,.1)", "hsl(0 0% 0%)", "oklch(0.5 0 0)", "oklab(0.5 0 0)", "color-mix(in srgb, red, blue)"])
      expect(hexColours("ui/src/design/base.css", `a { color: ${sample}; }`), sample).toHaveLength(1);
    expect(hexColours(own, `<i className="[color:color-mix(in_srgb,red,blue)]" />`)).toHaveLength(1);
    for (const cls of ["bg-black/10", "hover:text-white", "border-black", "fill-white"])
      expect(hexColours(own, `<i className="flex ${cls}" />`), cls).toHaveLength(1);
    expect(hexColours(own, `<i className="bg-background text-foreground whitespace-nowrap" />`)).toEqual([]);
  });

  it("left and right where a logical side exists", () => {
    for (const cls of ["ml-2", "hover:pr-4", "-left-1", "text-right", "border-l", "rounded-tr-lg", "md:float-left", "data-open:slide-in-from-left-2", "right-0!"])
      expect(physicalSides(own, `<div className="flex ${cls}" />`), cls).toHaveLength(1);
    expect(physicalSides(own, `<div style={{ marginLeft: 4 }} />`)).toHaveLength(1);
    expect(physicalSides(own, `<Popover side="right" />`)).toHaveLength(1);
    expect(physicalSides(own, `<i className="-translate-x-1/2" />`)).toHaveLength(1);
    expect(physicalSides(own, `<i className="-translate-x-1/2 rtl:translate-x-1/2" />`)).toEqual([]);
    expect(physicalSides("ui/src/design/base.css", "a { padding-left: 4px; text-align: right }")).toHaveLength(2);
    expect(physicalSides(own, `<div className="ms-2 pe-4 start-0 text-start border-s rounded-e-lg" />`)).toEqual([]);
    expect(physicalSides(copied, `"data-[side=left]:-right-1"`)).toEqual([]);
    expect(physicalSides(own, `"data-[side=left]:-right-1"`)).toHaveLength(1);
  });

  it("an import from the old interface", () => {
    expect(oldImports(own, `import { Shell } from "../shell/Shell";`)).toHaveLength(1);
    expect(oldImports(own, `import { t } from "../i18n";`)).toHaveLength(1);
    expect(oldImports(own, `import "../styles.css";`)).toHaveLength(2);
    expect(oldImports(own, `import { Button } from "@/ui/Button";`)).toHaveLength(1);
    expect(oldImports(own, `const m = await import("@/workspace/x");`)).toHaveLength(1);
    expect(oldImports(own, `import { api } from "@/api";`)).toHaveLength(1);
    expect(oldImports("ui/src/next/main.tsx", `import x from "../design/Thing";`)).toHaveLength(1);
    expect(
      oldImports(own, `import { cn } from "cn";\nimport type { Lang } from "@/texts/types";\nimport { X } from "./ui/button";\nimport "@/design/tokens.css";`),
    ).toEqual([]);
  });

  it("copper outside now/waiting", () => {
    expect(copperOutside(own, `<span className="text-now" />`)).toHaveLength(1);
    expect(copperOutside(own, `<span className="hover:bg-waiting/50" />`)).toHaveLength(1);
    expect(copperOutside(own, `<i style={{ color: "var(--copper)" }} />`)).toHaveLength(1);
    expect(copperOutside("ui/src/design/base.css", "a { color: var(--now); }")).toHaveLength(1);
    expect(copperOutside("ui/src/design/now-waiting.tsx", `"text-now"`)).toEqual([]);
    expect(copperOutside(own, `<span className="text-foreground" />`)).toEqual([]);
  });

  it("web storage", () => {
    for (const sample of ["localStorage.setItem('a', 'b')", "sessionStorage.clear()", "indexedDB.open('x')", "document.cookie = 'a=b'"])
      expect(webStorage(own, sample), sample).toHaveLength(1);
    expect(webStorage("ui/src/texts/language.test.ts", "vi.spyOn(window.localStorage, 'setItem')")).toEqual([]);
  });

  it("a shadow, gradient, blur, loop or slow state change", () => {
    for (const cls of ["shadow-md", "inset-shadow-sm", "drop-shadow-lg", "bg-linear-to-r", "from-black", "via-white", "to-transparent", "blur-sm", "backdrop-blur", "animate-pulse", "animate-in", "duration-300", "hover:duration-150", "shimmer"])
      expect(motionAndDepth(own, `<i className="flex ${cls}" />`), cls).not.toEqual([]);
    expect(motionAndDepth(own, `<i className="shadow-none duration-240 top-2 touch-none transition-colors" />`)).toEqual([]);
    expect(motionAndDepth(copied, `"data-open:animate-in data-open:fade-in-0 shadow-sm data-closed:animate-out"`)).toEqual([]);
    expect(motionAndDepth(copied, `"duration-100"`)).toHaveLength(1);
    expect(motionAndDepth(copied, `"backdrop-blur-xs"`)).toHaveLength(1);
    expect(motionAndDepth("ui/src/design/base.css", "a { box-shadow: 0 1px 2px var(--ink); background: linear-gradient(var(--ink), var(--paper)); }")).toHaveLength(2);
    expect(motionAndDepth("ui/src/design/base.css", "a { box-shadow: none; }")).toEqual([]);
  });

  it("tight leading, capitals, slant, small text and extra weights", () => {
    for (const cls of ["leading-none", "leading-[1.2]", "uppercase", "md:italic"]) {
      expect(typeRules(own, `<i className="flex ${cls}" />`), cls).toHaveLength(1);
      expect(typeRules(copied, `"flex ${cls}"`), cls).toHaveLength(1);
    }
    for (const cls of ["text-sm", "font-medium", "font-semibold", "font-light", "font-[600]", "tracking-wide"]) {
      expect(typeRules(own, `<i className="flex ${cls}" />`), cls).toHaveLength(1);
      expect(typeRules(copied, `"flex ${cls}"`), cls).toEqual([]);
    }
    expect(typeRules("ui/src/design/Wordmark.tsx", `"text-xs font-[600] tracking-[1px]"`)).toEqual([]);
    expect(typeRules(own, `<i className="text-xs text-base font-normal font-bold" />`)).toEqual([]);
  });

  it("opacity for disabled and dark:", () => {
    for (const cls of ["disabled:opacity-50", "data-disabled:opacity-50", "group-has-disabled/field:opacity-50", "aria-disabled:hover:opacity-60", "dark:bg-input/30"]) {
      expect(disabledAndDark(own, `<i className="flex ${cls}" />`), cls).toHaveLength(1);
      expect(disabledAndDark(copied, `"flex ${cls}"`), cls).toHaveLength(1);
    }
    expect(disabledAndDark(own, `<i className="opacity-0 data-disabled:text-muted-foreground" />`)).toEqual([]);
  });

  it("num beside a logical offset", () => {
    for (const cls of ["ms-2", "me-1", "ps-3", "pe-4", "start-0", "-end-1"])
      expect(numAlone(own, `<b className="num ${cls}" />`), cls).toHaveLength(1);
    expect(numAlone(own, `<b className="num text-end" />`)).toEqual([]);
  });

  it("a class for a token that does not exist", () => {
    for (const cls of ["bg-destructive", "aria-invalid:ring-destructive/20", "text-secondary-foreground", "bg-sidebar", "fill-chart-1", "bg-waiting-surface"])
      expect(missingTokens(copied, `"flex ${cls}"`), cls).toHaveLength(1);
    expect(missingTokens(own, `"not-data-[variant=destructive]:focus:text-accent-foreground"`)).toEqual([]);
  });

  it('dir="auto"', () => {
    expect(dirAuto(own, `<p dir="auto" />`)).toHaveLength(1);
    expect(dirAuto(own, `const props = { dir: "auto" };`)).toHaveLength(1);
    expect(dirAuto(own, `<p dir={textDir(body)} />`)).toEqual([]);
  });

  it("a file over 300 lines", () => {
    expect(tooLong(own, "x\n".repeat(301))).toHaveLength(1);
    expect(tooLong(own, "x\n".repeat(300))).toEqual([]);
  });
});
