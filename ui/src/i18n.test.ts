import { beforeEach, describe, expect, it } from "vitest";
import { count, counted, dir, language, pick, setLanguage, t, texts } from "./i18n";

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

  it("pick never throws on a text that is missing or half there", () => {
    expect(pick(undefined)).toBe("");
    expect(pick(null)).toBe("");
    expect(pick({ en: "Read" } as never, "ar")).toBe("Read");
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

  it("a count takes the form its number needs, in Arabic one, two, few and the rest", () => {
    expect(count("openComments", 1, {}, "ar")).toBe("ملاحظة واحدة مفتوحة");
    expect(count("openComments", 2, {}, "ar")).toBe("ملاحظتين مفتوحتين");
    expect(count("openComments", 3, {}, "ar")).toBe("3 ملاحظات مفتوحة");
    expect(count("openComments", 10, {}, "ar")).toBe("10 ملاحظات مفتوحة");
    expect(count("openComments", 11, {}, "ar")).toBe("11 ملاحظة مفتوحة");
    expect(count("openComments", 100, {}, "ar")).toBe("100 ملاحظة مفتوحة");
    expect(count("openComments", 1, {}, "en")).toBe("1 open comment");
    expect(count("openComments", 4, {}, "en")).toBe("4 open comments");
    expect(count("deskSummary", 2, { desk: "قسم - عينة" }, "ar")).toBe("قسم - عينة: اتنين شغالين");
  });

  it("every counted text has both languages and the same {placeholders} in every form", () => {
    const names = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).filter((n) => n !== "n");
    for (const [key, text] of Object.entries(counted)) {
      const all = [...Object.values(text.en), ...Object.values(text.ar)] as string[];
      for (const form of all) expect(names(form).sort(), key).toEqual(names(text.en.other).sort());
      expect(text.ar.other, key).toContain("{n}");
    }
  });

  it("a line that says where to change something later names the real buttons: those in the top bar's More", () => {
    // shell/TopBar.tsx: AI, the other language and Setup are in More, on every screen of the app
    const names = (key: keyof typeof texts) => ({ en: `“${texts[key].en}”`, ar: `«${texts[key].ar}»` });
    const where: [keyof typeof texts, (keyof typeof texts)[]][] = [
      ["languageHelp", ["more"]],
      ["usageHelp", ["setupAgain", "more"]],
      ["aiLinkLater", ["ai", "more"]],
    ];
    for (const [line, buttons] of where) {
      for (const button of buttons) {
        expect(texts[line].en, line).toContain(names(button).en);
        expect(texts[line].ar, line).toContain(names(button).ar);
      }
      expect(texts[line].en + texts[line].ar, line).not.toMatch(/in Settings|من الإعدادات|from the top bar/);
    }
  });
});
