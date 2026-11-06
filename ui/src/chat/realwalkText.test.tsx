import { render } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Reply } from "./Reply";
import { BidiText } from "./bidi";
import { FileName } from "../ui/FileName";

describe("real walk Arabic text (sample text)", () => {
  it("keeps Arabic replies RTL when ONE or a file name comes first, isolates clauses and dates", () => {
    const { container } = render(<Reply text={'ONE قرا ملف واحد:\n\nboq-priced.xlsx: مقايسة.\n\nالمحتجز (البند 14.3(iii)) بتاريخ 2026-11-06.'} />);
    for (const p of container.querySelectorAll("p")) expect(p).toHaveAttribute("dir", "rtl");
    expect(container.querySelector('bdi[dir="ltr"]')).toHaveTextContent("ONE");
    for (const text of ["boq-priced.xlsx", "14.3(iii)", "2026-11-06"]) {
      const run = [...container.querySelectorAll("bdi")].find((el) => el.textContent === text);
      expect(run).toHaveAttribute("dir", "ltr");
      if (text === "2026-11-06") expect(run).toHaveStyle({ whiteSpace: "nowrap" });
    }
  });
  it("follows the recorded reply language for every paragraph while code stays LTR", () => {
    const { container } = render(<Reply lang="ar" text={'BOQ قرا الملف.\n\nUnknownName: تفاصيل الملف.\n\n```\nqty = 5\n```'} />);
    for (const p of container.querySelectorAll("p")) expect(p).toHaveAttribute("dir", "rtl");
    expect(container.querySelector("pre")).toHaveAttribute("dir", "ltr");
    expect(container.querySelector("bdi")).toHaveAttribute("dir", "ltr");
  });
  it("keeps a date together in an English reply too", () => {
    const { container } = render(<Reply text="Date: 2026-11-06." />);
    expect(container.querySelector("bdi")).toHaveTextContent("2026-11-06");
    expect(container.querySelector("bdi")).toHaveStyle({ whiteSpace: "nowrap" });
  });
  it("keeps the engineer's own Arabic-Indic digits as typed", () => {
    const { container } = render(<BidiText text="زوّد الخرسانة ٥٪" preserveDigits />);
    expect(container.textContent).toBe("زوّد الخرسانة ٥٪");
  });
  it("keeps fitted Latin filenames LTR even in an Arabic card", () => {
    const { container } = render(<div dir="rtl"><FileName name="sample-boq-priced.xlsx" fit /></div>);
    expect(container.querySelector('[data-file-name]')).toHaveAttribute("dir", "ltr");
    expect(container.querySelector('[data-cut]')).toHaveAttribute("dir", "ltr");
  });
  it("lets the system draw typed Arabic digits: Zain draws these codepoints as Western glyphs", () => {
    const css = readFileSync(join(__dirname, "../styles.css"), "utf8");
    const faces = css.match(/@font-face\s*\{[^}]*font-family: "Zain"[^}]*\}/g)!;
    expect(faces).toHaveLength(3);
    for (const face of faces) {
      const ranges = [...face.matchAll(/U\+([0-9A-F]+)(?:-([0-9A-F]+))?/g)].map(([, a, b]) => [parseInt(a!, 16), parseInt(b ?? a!, 16)]);
      for (const digit of [0x660, 0x669, 0x6f0, 0x6f9]) expect(ranges.some(([a, b]) => digit >= a! && digit <= b!)).toBe(false);
    }
  });
});
