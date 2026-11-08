// The rows card of a BOQ import (core/qsone/tools/boq.py _card): one row per column of the sheet, each with what it
// holds; the engineer sets each column's meaning, and Keep sends them as answers by column letter (tender day,
// 5 Nov 2026: the card could only tick, and called the columns «الصفوف»).
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { ApprovalCard } from "./ApprovalCard";
import type { CardData } from "./types";

beforeEach(() => setLanguage("ar"));

const MEANINGS = ["code", "description", "description_2", "unit", "quantity", "rate", "amount", "none"];
const label: Record<string, { en: string; ar: string }> = {
  code: { en: "Item no.", ar: "رقم البند" },
  description: { en: "Description", ar: "الوصف" },
  description_2: { en: "Description, other language", ar: "الوصف باللغة التانية" },
  unit: { en: "Unit", ar: "الوحدة" },
  quantity: { en: "Quantity", ar: "الكمية" },
  rate: { en: "Rate", ar: "الفئة" },
  amount: { en: "Amount", ar: "الإجمالي" },
  none: { en: "Not used", ar: "مش مستخدم" },
};

const boq: CardData = {
  kind: "rows",
  title: { en: "Import the BOQ?", ar: "أستورد المقايسة؟" },
  detail: { en: "Check what each column holds.", ar: "راجع كل عمود فيه إيه." },
  options: ["keep", "no"],
  status: "pending",
  payload: {
    columns: [
      { key: "meaning", label: { en: "What it holds", ar: "فيه إيه" } },
      { key: "column", label: { en: "Column", ar: "العمود" } },
      { key: "header", label: { en: "Its heading in the file", ar: "عنوانه في الملف" } },
      { key: "example", label: { en: "First values", ar: "أول القيم" } },
    ],
    rows: [
      { column: "A", header: "رقم البند Item No.", example: "01-01-001", meaning: "none" },
      { column: "B", header: "الوصف / Description · عربي", example: "حفر - عينة", meaning: "description" },
      { column: "C", header: "الوصف / Description · English", example: "Excavation - sample", meaning: "unit" },
      { column: "D", header: "الوحدة Unit", example: "م3", meaning: "quantity" },
    ],
    meaning_column: "meaning",
    meanings: MEANINGS.map((key) => ({ key, label: label[key]! })),
    questions: ["A", "B", "C", "D"].map((id) => ({ id, text: id, options: MEANINGS })),
  },
};

function core() {
  const fetch = vi.fn(async () => new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("the BOQ columns card", () => {
  it("lets the engineer set each column's meaning, and sends them by letter", async () => {
    const fetch = core();
    const user = userEvent.setup();
    render(<ApprovalCard id="c9" card={boq} />);
    expect(screen.queryByRole("combobox")).toBeNull(); // folded: the columns ONE took, in one line
    await user.click(screen.getByRole("button", { name: texts.checkColumns.ar }));
    expect(screen.queryByRole("checkbox")).toBeNull(); // not ticks: a meaning per column
    const c = screen.getByRole("combobox", { name: "العمود C فيه إيه" });
    expect(c).toHaveValue("unit");
    await user.selectOptions(screen.getByRole("combobox", { name: "العمود A فيه إيه" }), "code");
    await user.selectOptions(c, "description_2");
    await user.selectOptions(screen.getByRole("combobox", { name: "العمود D فيه إيه" }), "unit");
    await user.click(screen.getByRole("button", { name: texts.keepColumns.ar }));
    const [, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      choice: "keep",
      answers: { A: "code", B: "description", C: "description_2", D: "unit" },
    });
    expect(await screen.findByText("ردّك: وافقت على 4 أعمدة")).toBeInTheDocument();
  });

  it("counts columns, not rows, once settled in the stream", () => {
    const answers = { A: "code", B: "description", C: "none", D: "unit" };
    render(<ApprovalCard id="c9" card={{ ...boq, status: "settled", choice: "keep", answers }} />);
    expect(screen.getByText("ردّك: وافقت على 3 أعمدة")).toBeInTheDocument();
  });

  it("never says «الصفوف» for columns", () => {
    render(<ApprovalCard id="c9" card={boq} />);
    expect(screen.queryByText(/الصفوف/)).toBeNull();
  });
});

it("shows only the header after a repeated tender title, without stripping distinct bilingual headings", () => {
  const card: CardData = { ...boq, payload: { ...boq.payload, rows: [
    { column: "D", header: "مقايسة عينة · الكمية الأصلية", meaning: "quantity" },
    { column: "F", header: "مقايسة عينة · إجمالي الكمية", meaning: "quantity" },
    { column: "G", header: "مقايسة عينة · الفئة", meaning: "rate" },
    { column: "I", header: "مقايسة عينة", meaning: "none" },
  ] } };
  render(<ApprovalCard id="sample-heading" card={card} />);
  fireEvent.click(screen.getByRole("button", { name: texts.checkColumns.ar }));
  expect(screen.queryAllByText(/مقايسة عينة ·/)).toHaveLength(0);
  expect(screen.getByText("الكمية الأصلية")).toBeInTheDocument();
  expect(screen.getByText("إجمالي الكمية")).toBeInTheDocument();
});
