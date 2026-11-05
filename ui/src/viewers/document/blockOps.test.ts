import { describe, expect, it } from "vitest";
import type { Block } from "../../deliverables/types";
import {
  blockText,
  displayValue,
  offsetAt,
  opsFor,
  pieces,
  type SlateElement,
} from "./blockOps";

const p = (text: string, id?: string): SlateElement => ({ type: "p", children: [{ text }], ...(id ? { id } : {}) });
const block = (id: string, version: number, node: SlateElement): Block => ({ id, version, node });
const total = { type: "cell", deliverable: "d1", row: "total", column: "amount", children: [{ text: "" }] };

describe("opsFor", () => {
  it("a changed paragraph becomes one set_block op with its version", () => {
    expect(opsFor([{ id: "b1", version: 2, node: p("الأسعار سارية لمدة ٣٠ يوماً") }], [p("الأسعار سارية لمدة ٤٥ يوماً", "b1")])).toEqual([
      { op: "set_block", block: "b1", node: p("الأسعار سارية لمدة ٤٥ يوماً", "b1"), expect: 2 },
    ]);
  });

  it("an unchanged document gives no ops, even after the editor's own normalising", () => {
    const before = [block("b1", 1, { type: "p", children: [total] }), block("b2", 1, p("نص - عينة"))];
    // Slate puts an empty text on each side of an inline and adds the block id
    const after: SlateElement[] = [
      { type: "p", id: "b1", children: [{ text: "" }, total, { text: "" }] },
      { type: "p", id: "b2", children: [{ text: "نص " }, { text: "- عينة" }] },
    ];
    expect(opsFor(before, after)).toEqual([]);
  });

  it("added, removed and moved blocks give insert, remove and move ops", () => {
    const before = [block("b1", 1, p("أ")), block("b2", 3, p("ب")), block("b3", 1, p("ج")), block("b4", 2, p("د"))];
    const after = [p("أ", "b1"), p("ج", "b3"), p("ب", "b2"), p("جديد - عينة")];
    expect(opsFor(before, after)).toEqual([
      { op: "move_block", block: "b3", after: "b1", expect: 1 },
      { op: "insert_block", after: "b2", node: p("جديد - عينة") },
      { op: "remove_block", block: "b4", expect: 2 },
    ]);
  });

  it("a split paragraph keeps its id on the first half; the second is a new block", () => {
    const after = [p("الأسعار سارية", "b1"), p("لمدة ٣٠ يوماً", "b1")];
    expect(opsFor([block("b1", 4, p("الأسعار سارية لمدة ٣٠ يوماً"))], after)).toEqual([
      { op: "set_block", block: "b1", node: p("الأسعار سارية", "b1"), expect: 4 },
      { op: "insert_block", after: "b1", node: p("لمدة ٣٠ يوماً") },
    ]);
  });

  it("new blocks in a row are sent last first, so accepting them in order keeps their order", () => {
    const after = [p("أول"), p("ثاني"), p("أ", "b1")];
    expect(opsFor([block("b1", 1, p("أ"))], after)).toEqual([
      { op: "insert_block", after: null, node: p("ثاني") },
      { op: "insert_block", after: null, node: p("أول") },
    ]);
  });

  it("only the template's keys go to the core: no nested ids, no stray marks", () => {
    const after: SlateElement[] = [
      {
        type: "ul",
        id: "b1",
        children: [{ type: "li", id: "x", children: [{ text: "بند", bold: true, suggestion: true, comment_1: true }] }],
      },
    ];
    const [op] = opsFor([block("b1", 1, { type: "ul", children: [{ type: "li", children: [{ text: "بند" }] }] })], after);
    expect(op).toEqual({
      op: "set_block",
      block: "b1",
      node: { type: "ul", id: "b1", children: [{ type: "li", children: [{ text: "بند", bold: true }] }] },
      expect: 1,
    });
  });
});

describe("block text and offsets", () => {
  const node: SlateElement = { type: "p", children: [{ text: "بإجمالي " }, total, { text: " جنيه" }] };

  it("joins the text leaves; a reference counts as no characters", () => {
    expect(blockText(node)).toBe("بإجمالي  جنيه");
  });

  it("splits a range over the leaves it covers", () => {
    expect(pieces(node, 2, 10)).toEqual([
      { path: [0], start: 2, end: 8 },
      { path: [2], start: 0, end: 2 },
    ]);
  });

  it("turns a point back into a block offset", () => {
    expect(offsetAt(node, [2], 3)).toBe(11);
    expect(offsetAt(node, [0], 1)).toBe(1);
  });
});

describe("displayValue", () => {
  const blocks = [block("b1", 1, p("الأسعار سارية حالياً لمدة ٣٠ يوماً")), block("b2", 1, p("ختام - عينة"))];

  it("puts each block's id on its element and keeps the rest as is", () => {
    expect(displayValue(blocks, [])).toEqual([p("الأسعار سارية حالياً لمدة ٣٠ يوماً", "b1"), p("ختام - عينة", "b2")]);
  });

  it("draws a pending change as Plate suggestion marks, whole words only", () => {
    const segments = [
      { op: "same" as const, text: "الأسعار سارية حالياً لمدة " },
      { op: "del" as const, text: "٣٠" },
      { op: "ins" as const, text: "٤٥" },
      { op: "same" as const, text: " يوماً" },
    ];
    const [first] = displayValue(blocks, [{ block: "b1", segments, changeId: "c1", author: "lead_qs" }]);
    expect(first!.id).toBe("b1");
    expect(first!.children).toEqual([
      { text: "الأسعار سارية حالياً لمدة " },
      { text: "٣٠", suggestion: true, suggestion_c1: { id: "c1", type: "remove", userId: "lead_qs", createdAt: 0 } },
      { text: "٤٥", suggestion: true, suggestion_c1: { id: "c1", type: "insert", userId: "lead_qs", createdAt: 0 } },
      { text: " يوماً" },
    ]);
  });

  it("places a suggested new block after the block it follows", () => {
    const value = displayValue(blocks, [
      { block: "new:c2", after: "b1", segments: [{ op: "ins", text: "فقرة جديدة" }], changeId: "c2", author: "lead_qs" },
    ]);
    expect(value.map((e) => e.id)).toEqual(["b1", "new:c2", "b2"]);
  });
});
