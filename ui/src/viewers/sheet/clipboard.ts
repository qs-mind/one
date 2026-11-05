// Copy and paste of several cells with Excel and LibreOffice, ours: react-data-grid copies one cell only.
// Copy writes tab-separated text and an HTML table; a paste becomes typed operations, one per cell, and the
// cells that cannot take a value are listed in plain words.
import type { Op, ViewColumn, ViewRow } from "../../deliverables/types";
import { isNumber } from "../../deliverables/types";
import { texts, type Text } from "../../i18n";
import { titleColumnOf } from "./heights";
import type { Cell } from "./selection";

const quoted = (value: string) => (/[\t\n\r"]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value);

export function toTsv(values: string[][]): string {
  return values.map((row) => row.map(quoted).join("\t")).join("\r\n");
}

const escape = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function toHtml(values: string[][], dir: "rtl" | "ltr"): string {
  const rows = values.map((row) => `<tr>${row.map((v) => `<td>${escape(v)}</td>`).join("")}</tr>`);
  return `<table dir="${dir}">${rows.join("")}</table>`;
}

/** Excel's clipboard text: tabs between cells, \r\n or \n between rows, a trailing newline, and quoted
 * fields that may hold tabs, line breaks and doubled quotes. A field not starting with a quote is literal. */
export function parseTsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let i = 0;
  const endRow = () => {
    rows.push(row);
    row = [];
  };
  while (i <= text.length) {
    let field = "";
    if (text[i] === '"') {
      i += 1;
      while (i < text.length) {
        if (text[i] === '"' && text[i + 1] === '"') {
          field += '"';
          i += 2;
        } else if (text[i] === '"') {
          i += 1;
          break;
        } else field += text[i++];
      }
      while (i < text.length && !"\t\r\n".includes(text[i]!)) field += text[i++]; // text after the closing quote
    } else {
      while (i < text.length && !"\t\r\n".includes(text[i]!)) field += text[i++];
    }
    row.push(field);
    if (text[i] === "\t") i += 1;
    else {
      if (text[i] === "\r") i += 1;
      if (text[i] === "\n") i += 1;
      endRow();
      if (i >= text.length) break; // a trailing newline ends the last row; it does not start one
    }
  }
  return rows;
}

const DIGITS: Record<string, string> = Object.fromEntries(
  [..."٠١٢٣٤٥٦٧٨٩", ..."۰۱۲۳۴۵۶۷۸۹"].map((d, i) => [d, String(i % 10)]),
);

/** A pasted number as the ledger takes it: «٣٩٨٥٠٫٥٠» -> "39850.50", "39,850.50" -> "39850.50". Never a float. */
export function pastedNumber(text: string): string | null {
  let s = text.replace(/[\s ‎‏؜]/g, "");
  s = s.replace(/[٠-٩۰-۹]/g, (d) => DIGITS[d]!).replace(/٫/g, ".").replace(/٬/g, ",");
  const match = /^(-?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?$/.exec(s);
  if (!match) return null;
  return `${match[1]}${match[2]!.replace(/,/g, "")}${match[3] ?? ""}`;
}

/** The ledger number a number column shows: `number:rate` -> "rate"; without `from`, the column key. */
export function numberName(column: ViewColumn): string {
  return column.from?.startsWith("number:") ? column.from.slice("number:".length) : column.key;
}

/** The item field a text column shows: `field:description` -> "description"; without `from`, the column key. */
export function fieldKey(column: ViewColumn): string {
  return column.from?.startsWith("field:") ? column.from.slice("field:".length) : column.key;
}

/** What a cell holds as plain text, as it is copied and edited: numbers as their exact decimal string. */
export function cellText(row: ViewRow, column: ViewColumn, titleColumn: string | undefined): string {
  if (row.kind === "section" && column.key === titleColumn) return row.title ?? "";
  if (column.from === "code" || (column.from === undefined && column.key === "code")) return row.code ?? "";
  const cell = row.cells[column.key];
  if (!cell) return "";
  return isNumber(cell) ? cell.value : cell.text;
}

/** Whether the engineer may type in this cell: a section's title, or an editable item column that is not calculated. */
export function why(row: ViewRow, column: ViewColumn, titleColumn: string | undefined): Text | null {
  if (row.kind === "section") return column.key === titleColumn ? null : texts.sheetNotEditable;
  if (column.kind === "calc") return texts.sheetAmountComputed;
  return column.edit ? null : texts.sheetNotEditable;
}

/** One cell's typed value as an operation, or why it cannot take it; null when nothing would change. */
function opFor(row: ViewRow, column: ViewColumn, text: string, titleColumn: string | undefined): Op | Text | null {
  if (text.trim() === "" || text === cellText(row, column, titleColumn)) return null;
  const refused = why(row, column, titleColumn);
  if (refused) return refused;
  if (row.kind === "section") return { op: "set_section_title", row: row.id, title: text, expect: row.version };
  if (column.kind === "number") {
    const value = pastedNumber(text);
    const cell = row.cells[column.key];
    const now = isNumber(cell) ? cell : null;
    if (value === null) return texts.sheetNotNumber;
    if (value === now?.value) return null;
    return {
      op: "set_number",
      row: row.id,
      name: numberName(column),
      value,
      ...(now?.unit ? { unit: now.unit } : {}),
      ...(now?.currency ? { currency: now.currency } : {}),
      expect: now?.number_id ?? null,
    };
  }
  return { op: "set_field", row: row.id, key: fieldKey(column), value: text, expect: row.item_version ?? null };
}

/** A pasted block of cells, from `at` (top-left) onwards, over the rows shown and the columns in screen order. */
export function pasteOps(
  at: Cell,
  grid: string[][],
  rows: ViewRow[],
  columns: ViewColumn[],
): { ops: Op[]; refused: { cell: Cell; why: Text }[] } {
  const titleColumn = titleColumnOf(columns);
  const ops: Op[] = [];
  const refused: { cell: Cell; why: Text }[] = [];
  grid.forEach((values, i) =>
    values.forEach((text, j) => {
      const cell = { row: at.row + i, col: at.col + j };
      const row = rows[cell.row];
      const column = columns[cell.col];
      if (!row || !column) return; // past the sheet's edge
      const out = opFor(row, column, text, titleColumn);
      if (out === null) return;
      if ("op" in out) ops.push(out);
      else refused.push({ cell, why: out });
    }),
  );
  return { ops, refused };
}
