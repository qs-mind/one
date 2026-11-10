// @vitest-environment node
// The design rules (@/design/test/rules.ts) over the frame's own files. ui/src/app also holds the old interface's
// start screen, so the folder is not one of NEW_UI_ROOTS; its imports (the contract client, the places) are checked
// by the typecheck instead of the old-imports rule.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { RULES } from "@/design/test/rules";

const FILES = ["App.tsx", "Frame.tsx", "gates.tsx", "paths.ts", "routes.tsx", "Frame.test.tsx", "routes.test.tsx"];
const { oldImports: _old, ...rules } = RULES;

describe("the frame keeps the design rules", () => {
  it.each(Object.entries(rules))("%s", (_name, rule) => {
    const problems = FILES.flatMap((name) => rule(`ui/src/app/${name}`, readFileSync(new URL(name, import.meta.url), "utf8")));
    expect(problems).toEqual([]);
  });
});
