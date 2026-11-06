// Where something sits in a Deliverable, in plain words for the review panels and the canvas selection: an item's
// code, a section's title, the total, a quoted passage. Never a part id. Labels follow the screen language.
import type { CommentAnchor, View, ViewCell, ViewColumn } from "../deliverables/types";
import { isNumber } from "../deliverables/types";
import { fill, language, pick, t, texts, type Language } from "../i18n";
import { blockText, type SlateElement } from "../viewers/document/blockOps";
import { formatDecimal } from "../viewers/sheet/format";
import { unitText } from "../sources/SourceCard";

const TOTAL = "total"; // the core's row for the bill total

const short = (text: string, max = 40) => (text.length > max ? `${text.slice(0, max).trimEnd()}…` : text);

/** A sheet row's name (its code, a section's title, the total) or a block's first words. */
export function rowName(view: View, row: string | null | undefined, lang: Language = language()): string {
  if (row === TOTAL) return pick(texts.sheetTotal, lang);
  if (!row) return pick(texts.placeParagraph, lang);
  if (view.kind === "sheet") {
    const found = view.rows.find((r) => r.id === row);
    return found ? (found.code ?? found.title ?? "") : "";
  }
  if (view.kind === "pack") return view.title;
  const block = view.blocks.find((b) => b.id === row);
  const text = block ? blockText(block.node as SlateElement).trim() : "";
  return text ? fill(pick(texts.placeQuote, lang), { quote: short(text, 30) }) : pick(texts.placeParagraph, lang);
}

/** A column's label in the screen language; for a Document's reference key, nothing. */
export function columnName(view: View, column: string, lang: Language = language()): string {
  if (view.kind !== "sheet") return "";
  const found: ViewColumn | undefined = view.columns.find((c) => c.key === column);
  return found ? pick(found.label, lang) : "";
}

/** «البند 03/02، الفئة»: a row and, when given, a column. */
export function cellPlace(view: View, row: string | null, column?: string, lang: Language = language()): string {
  const name = rowName(view, row, lang);
  const isItem = view.kind === "sheet" && view.rows.some((r) => r.id === row && r.kind === "item");
  const place = isItem ? fill(pick(texts.placeItem, lang), { code: name }) : name;
  const col = column ? columnName(view, column, lang) : "";
  return col ? fill(pick(texts.placeCell, lang), { place, column: col }) : place;
}

/** «البنود 03/01–03/04» for rows from → to, or one row's place when they are the same. */
export function rangePlace(view: View, from: string, to: string, column?: string, lang: Language = language()): string {
  if (from === to) return cellPlace(view, from, column, lang);
  return fill(pick(texts.placeItems, lang), { from: rowName(view, from, lang), to: rowName(view, to, lang) });
}

/** Where a comment sits now, in plain words. */
export function anchorPlace(view: View, anchor: CommentAnchor, lang: Language = language()): string {
  let place: string;
  switch (anchor.type) {
    case "cell":
      place = cellPlace(view, anchor.row, anchor.column, lang);
      break;
    case "range":
      place = rangePlace(view, anchor.from.row, anchor.to.row, anchor.from.column, lang);
      break;
    case "row":
      place = cellPlace(view, anchor.row ?? anchor.block ?? null, undefined, lang);
      break;
    case "text":
      place = fill(pick(texts.placeQuote, lang), { quote: short(anchor.quote) });
      break;
    default:
      place = pick(texts.placeWhole, lang);
  }
  return anchor.moved ? fill(pick(texts.placeMoved, lang), { place }) : place;
}

/** A cell's value as plain text («39,850.50 ج.م.» in Arabic, as the page writes money; a text; or «—» when there is
 * none: never 0). */
export function cellValue(cell: ViewCell | null | undefined): string {
  if (!cell) return "—";
  if (isNumber(cell)) {
    const unit = cell.currency ?? cell.unit;
    return `${formatDecimal(cell.value, cell.currency ? 2 : undefined)}${unit ? ` ${unitText(unit)}` : ""}`;
  }
  return cell.text;
}

/** Who made a change or a comment, as a role name: You, Lead QS, Checking QS, QS Calc Engine, or the specialist's
 * own name. */
export function authorName(author: string): string {
  switch (author) {
    case "engineer":
      return t("reviewYou");
    case "lead_qs":
      return t("roleLead");
    case "checking_qs":
      return t("roleChecker");
    case "calc_engine":
      return t("reviewCalcEngine");
    default:
      return author;
  }
}

/** A date and time from the core, in the screen language. */
export function when(at: string): string {
  const date = new Date(at.replace(/(\.\d{3})\d+/, "$1")); // the core sends microseconds; not every engine reads them
  if (Number.isNaN(date.getTime())) return at;
  return new Intl.DateTimeFormat(language() === "ar" ? "ar-EG-u-nu-latn" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
