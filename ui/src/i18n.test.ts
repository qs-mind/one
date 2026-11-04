import { beforeEach, describe, expect, it } from "vitest";
import { dir, language, setLanguage, t, texts } from "./i18n";

beforeEach(() => setLanguage("ar"));

describe("i18n", () => {
  it("Arabic sets rtl on the page", () => {
    setLanguage("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(document.documentElement.lang).toBe("ar");
    expect(dir()).toBe("rtl");
    expect(t("send")).toBe(texts.send.ar);
  });

  it("English sets ltr on the page", () => {
    setLanguage("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(document.documentElement.lang).toBe("en");
    expect(t("send")).toBe(texts.send.en);
  });

  it("remembers the choice", () => {
    setLanguage("en");
    expect(localStorage.getItem("qsone.language")).toBe("en");
    expect(language()).toBe("en");
  });

  it("every text has both languages", () => {
    for (const text of Object.values(texts)) {
      expect(text.en.trim()).not.toBe("");
      expect(text.ar.trim()).not.toBe("");
    }
  });

  it("every text has the same {placeholders} in both languages", () => {
    const names = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    for (const [key, text] of Object.entries(texts)) {
      expect(names(text.ar), key).toEqual(names(text.en));
    }
  });

  it("has the Deliverables labels in their groups (Plan 6)", () => {
    const keys = Object.keys(texts);
    for (const group of ["sheet", "doc", "review", "export", "fill", "status"]) {
      expect(keys.filter((k) => k.startsWith(group)).length, group).toBeGreaterThan(1);
    }
    expect(texts.deliverables).toEqual({ en: "Project Index", ar: "فهرس المشروع" });
    expect(texts.reviewRecordsMoved.ar).toBe("تحديث من سجلات المشروع");
    expect(texts.exportDraftMark.ar).toBe("مسودة — غير معتمد");
    expect(texts.sheetSample.ar).toContain("بيانات تجريبية");
  });
});
