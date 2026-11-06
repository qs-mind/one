// The Sheet viewer's pure logic: range selection, clipboard, section collapse, row heights and number format.
import { describe, expect, it } from "vitest";
import { texts } from "../../i18n";
import type { ViewColumn, ViewRow } from "../../deliverables/types";
import { pasteOps, parseTsv, pastedNumber, toHtml, toTsv } from "./clipboard";
import { visibleRows } from "./collapse";
import { formatDecimal } from "./format";
import { textScale } from "../../ui/scale";
import { COMPACT_PAD, linesHeight, oneLineWidth, rowHeight, shownWidth } from "./heights";
import { extend, normalised } from "./selection";

const size = { rows: 10, cols: 6 };

const columns: ViewColumn[] = [
  { key: "code", label: { en: "Item", ar: "البند" }, kind: "text", edit: false, frozen: true, wrap: false, width: 70, from: "code" },
  { key: "description", label: { en: "Description", ar: "بيان الأعمال" }, kind: "text", edit: true, frozen: false, wrap: true, width: 420, from: "field:description" },
  { key: "unit", label: { en: "Unit", ar: "الوحدة" }, kind: "text", edit: false, frozen: false, wrap: false, width: 60, from: "number:quantity.unit" },
  { key: "quantity", label: { en: "Qty", ar: "الكمية" }, kind: "number", edit: true, frozen: false, wrap: false, width: 90, from: "number:quantity" },
  { key: "rate", label: { en: "Rate", ar: "الفئة" }, kind: "number", edit: true, frozen: false, wrap: false, width: 110, from: "number:rate" },
  { key: "amount", label: { en: "Amount", ar: "الإجمالي" }, kind: "calc", edit: false, frozen: false, wrap: false, width: 130, from: "number:amount" },
];

const num = (value: string, id: string, more: object = {}) => ({
  value,
  number_id: id,
  source: "s1",
  dated: "2026-11-01",
  ...more,
});

const section = (id: string, title: string, level = 1): ViewRow => ({
  id,
  kind: "section",
  level,
  item_id: `i-${id}`,
  title,
  version: 1,
  cells: { amount: num("100.00", `n-${id}`, { currency: "EGP", calculated: true }) },
});
const item = (id: string, code: string, more: Partial<ViewRow["cells"]> = {}): ViewRow => ({
  id,
  kind: "item",
  item_id: `i-${id}`,
  item_version: 3,
  version: 1,
  code,
  cells: {
    description: { text: "خرسانة عادية - عينة" },
    unit: { text: "m3" },
    quantity: num("120", `q-${id}`, { unit: "m3" }),
    rate: num("39850.50", `r-${id}`, { unit: "m3", currency: "EGP" }),
    amount: num("4782060.00", `a-${id}`, { currency: "EGP", calculated: true }),
    ...more,
  } as ViewRow["cells"],
});

describe("selection", () => {
  it("extends a range with mirrored arrows in Arabic", () => {
    const r = { anchor: { row: 2, col: 3 }, focus: { row: 2, col: 3 } };
    expect(extend(r, "ArrowLeft", "rtl", size).focus).toEqual({ row: 2, col: 4 }); // left is the next column in RTL
    expect(extend(r, "ArrowLeft", "ltr", size).focus).toEqual({ row: 2, col: 2 });
    expect(extend(r, "ArrowRight", "rtl", size).focus).toEqual({ row: 2, col: 2 });
    expect(extend(r, "ArrowDown", "rtl", size)).toEqual({ anchor: r.anchor, focus: { row: 3, col: 3 } });
  });

  it("stops at the sheet's edges", () => {
    const corner = { anchor: { row: 0, col: 0 }, focus: { row: 0, col: 0 } };
    expect(extend(corner, "ArrowUp", "ltr", size).focus).toEqual({ row: 0, col: 0 });
    expect(extend(corner, "ArrowRight", "rtl", size).focus).toEqual({ row: 0, col: 0 });
    const end = { anchor: { row: 9, col: 5 }, focus: { row: 9, col: 5 } };
    expect(extend(end, "ArrowDown", "ltr", size).focus).toEqual({ row: 9, col: 5 });
    expect(extend(end, "ArrowLeft", "rtl", size).focus).toEqual({ row: 9, col: 5 });
  });

  it("normalises a range dragged up and backwards", () => {
    expect(normalised({ anchor: { row: 5, col: 4 }, focus: { row: 2, col: 1 } })).toEqual({
      top: 2,
      bottom: 5,
      start: 1,
      end: 4,
    });
  });
});

describe("clipboard", () => {
  it("pastes Excel text as exact numbers", () => {
    expect(parseTsv('11\t"a\nb"\r\n22\t3\r\n')).toEqual([
      ["11", "a\nb"],
      ["22", "3"],
    ]);
    expect(parseTsv('say ""hi""\t"x ""y"""')).toEqual([['say ""hi""', 'x "y"']]);
    expect(parseTsv("5")).toEqual([["5"]]);
    expect(pastedNumber("٣٩٨٥٠٫٥٠")).toBe("39850.50");
    expect(pastedNumber("39,850.50")).toBe("39850.50");
    expect(pastedNumber(" 120 ")).toBe("120");
    expect(pastedNumber("-0.5")).toBe("-0.5");
    expect(pastedNumber("۱۲۰")).toBe("120");
    expect(pastedNumber("abc")).toBeNull();
    expect(pastedNumber("1,2")).toBeNull();
    expect(pastedNumber("1.2.3")).toBeNull();
    expect(pastedNumber("")).toBeNull();
  });

  it("copies the range as TSV and an RTL HTML table", () => {
    const values = [
      ["03/02", "خرسانة <عادية>", "39850.50"],
      ["1-1", 'سطر\nثاني "مقتبس"', "14"],
    ];
    const tsv = toTsv(values);
    expect(tsv).toBe('03/02\tخرسانة <عادية>\t39850.50\r\n1-1\t"سطر\nثاني ""مقتبس"""\t14');
    expect(parseTsv(tsv)).toEqual(values);
    const html = toHtml(values, "rtl");
    expect(html).toContain('<table dir="rtl">');
    expect(html).toContain("<td>خرسانة &lt;عادية&gt;</td>");
    expect(html).toContain("<td>39850.50</td>");
    expect(html.match(/<tr>/g)).toHaveLength(2);
    expect(toHtml([["a"]], "ltr")).toContain('<table dir="ltr">');
  });

  it("a paste over the amount column is refused, the rest become ops", () => {
    const rows = [item("p2", "03/02"), item("p3", "03/03")];
    const { ops, refused } = pasteOps({ row: 0, col: 4 }, [["40000", "1"], ["٣٩٨٥١٫٠٠", "2"]], rows, columns);
    expect(ops).toEqual([
      { op: "set_number", row: "p2", name: "rate", value: "40000", unit: "m3", currency: "EGP", expect: "r-p2" },
      { op: "set_number", row: "p3", name: "rate", value: "39851.00", unit: "m3", currency: "EGP", expect: "r-p3" },
    ]);
    expect(refused).toEqual([
      { cell: { row: 0, col: 5 }, why: texts.sheetAmountComputed },
      { cell: { row: 1, col: 5 }, why: texts.sheetAmountComputed },
    ]);
  });

  it("text goes to fields, section titles to their section, and code and words in numbers are refused", () => {
    const rows = [section("p1", "أعمال الحفر"), item("p2", "1-1", { quantity: { text: "فئة فقط" } })];
    const { ops, refused } = pasteOps(
      { row: 0, col: 0 },
      [
        ["x", "أعمال الحفر والردم", "m3", "5"],
        ["9-9", "حفر - عينة", "m2", "كتير"],
      ],
      rows,
      columns,
    );
    expect(ops).toEqual([
      { op: "set_section_title", row: "p1", title: "أعمال الحفر والردم", expect: 1 },
      { op: "set_field", row: "p2", key: "description", value: "حفر - عينة", expect: 3 },
    ]);
    expect(refused).toEqual([
      { cell: { row: 0, col: 0 }, why: texts.sheetNotEditable },
      { cell: { row: 0, col: 2 }, why: texts.sheetNotEditable },
      { cell: { row: 0, col: 3 }, why: texts.sheetNotEditable },
      { cell: { row: 1, col: 0 }, why: texts.sheetNotEditable },
      { cell: { row: 1, col: 2 }, why: texts.sheetNotEditable },
      { cell: { row: 1, col: 3 }, why: texts.sheetNotNumber },
    ]);
  });

  it("a number pasted where there is none yet expects none; unchanged and empty cells are skipped", () => {
    const rows = [item("p2", "1-1", { quantity: { text: "فئة فقط" } })];
    expect(pasteOps({ row: 0, col: 3 }, [["120", "39850.50"]], rows, columns)).toEqual({
      ops: [{ op: "set_number", row: "p2", name: "quantity", value: "120", expect: null }],
      refused: [],
    });
    expect(pasteOps({ row: 0, col: 3 }, [["", "39850.50", "1"]], rows, columns).ops).toEqual([]);
    expect(pasteOps({ row: 5, col: 9 }, [["1"]], rows, columns)).toEqual({ ops: [], refused: [] }); // off the sheet
  });
});

describe("collapse", () => {
  it("collapsing a section hides its items until the next section", () => {
    const rows = [
      section("s1", "أعمال الحفر"),
      item("a", "1-1"),
      item("b", "1-2"),
      section("s2", "أعمال الخرسانة"),
      section("s21", "خرسانة عادية", 2),
      item("c", "2-1"),
      section("s22", "خرسانة مسلحة", 2),
      item("d", "2-2"),
      section("s3", "أعمال البياض"),
      item("e", "3-1"),
    ];
    const ids = (collapsed: string[]) => visibleRows(rows, new Set(collapsed)).map((r) => r.id);
    expect(ids([])).toEqual(rows.map((r) => r.id));
    expect(ids(["s1"])).toEqual(["s1", "s2", "s21", "c", "s22", "d", "s3", "e"]);
    expect(ids(["s2"])).toEqual(["s1", "a", "b", "s2", "s3", "e"]);
    expect(ids(["s21"])).toEqual(["s1", "a", "b", "s2", "s21", "s22", "d", "s3", "e"]);
    expect(ids(["s3", "s1"])).toEqual(["s1", "s2", "s21", "c", "s22", "d", "s3"]);
  });
});

describe("heights", () => {
  const measure = (text: string) => text.length * 7;

  it("a long Arabic description gets a taller row", () => {
    const short = item("p1", "1-1");
    const long = item("p2", "1-2", {
      description: { text: "بالمتر المكعب توريد وصب خرسانة عادية - عينة ".repeat(12).trim() },
    });
    const base = rowHeight(short, columns, measure);
    const tall = rowHeight(long, columns, measure);
    expect(base).toBe(linesHeight(1));
    expect(tall).toBeGreaterThan(base * 3);
    expect(Number.isInteger((tall - linesHeight(0)) / (linesHeight(2) - linesHeight(1)))).toBe(true); // whole lines
  });

  it("wraps by words, so a word never breaks across lines", () => {
    const words = item("p1", "1-1", { description: { text: "ممم ممم" } });
    // each word is 21 px; the column holds 420 - padding, so both fit on one line
    expect(rowHeight(words, columns, measure)).toBe(linesHeight(1));
    const narrow = columns.map((c) => (c.key === "description" ? { ...c, width: 40 } : c));
    expect(rowHeight(words, narrow, measure)).toBe(linesHeight(2));
  });

  it("a section row measures its title in bold", () => {
    const fonts: string[] = [];
    rowHeight(section("s1", "أعمال الحفر"), columns, (text, font) => {
      fonts.push(font);
      return text.length * 7;
    });
    expect(fonts.some((f) => f.startsWith("700"))).toBe(true);
  });

  it("at a smaller scale the rows are measured as the cells are drawn: the padding at the screen's scale, the text at its floor", () => {
    const sizes = { space: 0.8, text: textScale(0.8, "ar") }; // 1280×720, Arabic
    expect(linesHeight(1, COMPACT_PAD)).toBe(32); // 100 %: the open document's one-line row
    expect(linesHeight(1, COMPACT_PAD, sizes)).toBeCloseTo(24 * 0.9 + 8 * 0.8, 10);
    expect(linesHeight(3, COMPACT_PAD, sizes)).toBeCloseTo(3 * 24 * 0.9 + 8 * 0.8, 10);
    const fonts: string[] = [];
    rowHeight(item("p1", "1-1"), columns, (text, font) => (fonts.push(font), text.length * 7), COMPACT_PAD, sizes);
    expect(fonts[0]).toMatch(/^13\.5px /); // the grid's 15 px at Arabic's floor, as styles.css draws it
  });

  it("at a smaller scale a column is narrower on screen, and a one-line column still holds its longest value", () => {
    const sizes = { space: 0.8, text: textScale(0.8, "en") };
    expect(shownWidth(100)).toBe(112);
    expect(shownWidth(100, sizes)).toBeCloseTo(89.6, 10);
    const code = { key: "code", label: { en: "Item", ar: "البند" }, kind: "text" as const, edit: false, frozen: true, wrap: false, width: 40 };
    const rows = [item("p1", "02-01-001-0001")];
    const measured = (text: string, font: string) => text.length * parseFloat(font) * 0.5;
    const width = oneLineWidth(code, "Item", rows, measured, [], sizes);
    const longest = measured("02-01-001-0001", `${15 * sizes.text}px x`);
    expect(shownWidth(width, sizes)).toBeGreaterThanOrEqual(longest + 24 * 0.8);
  });
});

describe("format", () => {
  it("formats decimals without floats", () => {
    expect(formatDecimal("12345678901234567.10", 2)).toBe("12,345,678,901,234,567.10");
    expect(formatDecimal("39850.5", 2)).toBe("39,850.50");
    expect(formatDecimal("4782060", 2)).toBe("4,782,060.00");
    expect(formatDecimal("120")).toBe("120");
    expect(formatDecimal("5555")).toBe("5,555");
    expect(formatDecimal("-1234.5")).toBe("-1,234.5");
    expect(formatDecimal("0.125", 2)).toBe("0.125"); // never cuts a digit the ledger holds
    expect(formatDecimal("999")).toBe("999");
  });
});
