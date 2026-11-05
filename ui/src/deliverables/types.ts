// What the core sends about Deliverables (Plan 6, Tasks 2–7). Numbers are always decimal strings, never floats.
import type { Language, Text } from "../i18n";

export type Status = "draft" | "checked" | "signed_off";
export type Code = "A" | "B" | "C";

/** One entry of GET /projects/{p}/deliverables: Plan 7's DeliverableInfo plus pending, total and sample. */
export type DeliverableInfo = {
  id: string;
  kind: "sheet" | "document" | "markup" | "board" | "page";
  title: string;
  language: Language;
  status: Status;
  code: Code | null;
  same_provider: boolean;
  revision: number | null;
  desk: Text | null;
  off_desk: boolean;
  progress: { done: number; total: number } | null;
  open_comments: number;
  updated_at: string;
  pending?: number;
  total?: NumberCell | null;
  sample?: boolean;
};

export type Source = {
  kind: string; // "sample", "engineer", "calculation", "file", …
  title: string;
  file_name?: string | null;
  /** The file in Project Records, for the jump to its frame. */
  file_id?: string | null;
  locator: Record<string, string | number>;
  url?: string | null;
  dated?: string | null;
};

/** A cell that shows a ledger number. */
export type NumberCell = {
  value: string;
  unit?: string | null;
  currency?: string | null;
  /** Null in what a pending change would write: the dry run that made the number was rolled back. */
  number_id: string | null;
  source: string | null;
  dated: string | null;
  calculated?: boolean;
};
/** A cell that shows text: a field, a unit, or the note that stands in for a missing number («فئة فقط»). */
export type TextCell = { text: string };
export type ViewCell = NumberCell | TextCell;

export const isNumber = (cell: ViewCell | null | undefined): cell is NumberCell =>
  typeof (cell as NumberCell | undefined)?.value === "string";

export type ViewColumn = {
  key: string;
  label: Text;
  kind: "text" | "number" | "calc";
  edit: boolean;
  frozen: boolean;
  wrap: boolean;
  width: number;
  /** The template's `from` (`code`, `field:<key>`, `number:<name>`, `number:<name>.unit`), when the core sends it. */
  from?: string;
};

export type ViewRow = {
  id: string; // the part id
  kind: "section" | "item";
  level?: number;
  item_id: string;
  item_version?: number;
  version: number; // the part version
  code?: string;
  title?: string; // a section's title
  cells: Record<string, ViewCell>;
};

type ViewHead = {
  id: string;
  variant: string;
  title: string;
  language: Language;
  status: Status;
  code: Code | null;
  same_provider: boolean;
  off_desk: boolean;
  version: number;
  at: string;
  revision: { no: number; version: number; signed_off: boolean } | null;
  sample: boolean;
  sources: Record<string, Source>;
  pending: number;
  open_comments: number;
  records_moved: boolean;
  progress?: { done: number; total: number } | null;
};

export type SheetView = ViewHead & {
  kind: "sheet";
  columns: ViewColumn[];
  rows: ViewRow[];
  total: NumberCell | null;
  incomplete: Record<string, number>;
};

export type Block = { id: string; version: number; node: Record<string, unknown> };
export type RefValue = NumberCell;

export type DocumentView = ViewHead & {
  kind: "document";
  blocks: Block[];
  refs: Record<string, RefValue>;
  untraced: { block: string; text: string }[];
};

export type View = SheetView | DocumentView;

/** One typed operation, held as a Suggested change until the engineer accepts it. */
export type NumberIn = { name: string; value: string; unit?: string; currency?: string; source_id?: string; dated?: string };
export type Op =
  | { op: "set_number"; row: string; name: string; value: string; unit?: string; currency?: string; source_id?: string; dated?: string; expect: string | null }
  | { op: "set_field"; row: string; key: string; value: string; expect: number | null }
  | { op: "add_item_row"; after: string | null; code: string; fields: Record<string, string>; numbers: NumberIn[] }
  | { op: "add_section"; after: string | null; title: string; level: number }
  | { op: "set_section_title"; row: string; title: string; expect: number }
  | { op: "remove_row"; row: string; expect: number }
  | { op: "move_row"; row: string; after: string | null; expect: number }
  | { op: "set_columns"; columns: unknown[]; expect: number }
  | { op: "set_block"; block: string; node: Record<string, unknown>; expect: number }
  | { op: "insert_block"; after: string | null; node: Record<string, unknown> }
  | { op: "remove_block"; block: string; expect: number }
  | { op: "move_block"; block: string; after: string | null; expect: number }
  | { op: "update_from_records"; cells: RecordsCell[]; expect?: unknown };

/** A cell a change touches. `row` is a part id, or "total" for the bill total; in a Document, `row` is the block
 * (null when the reference is in no block) and `column` the reference key. */
export type CellChange = { row: string | null; column: string; before: ViewCell | null; after: ViewCell | null };
/** Why a cell moved in Project Records: corrected (with the reason, null for an item field) or recalculated. */
export type RecordsCell = CellChange & { why: { corrected: string | null } | { recalculated: true } };

export type Change = {
  id: string;
  deliverable_id: string;
  op: Op;
  reason: string | null;
  author: string;
  comment_id: string | null;
  status: "pending" | "accepted" | "rejected" | "stale";
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  version_n: number | null;
  /** What the change shows, old and new: a cell for a number, field or section title; a Block for a Document op;
   * a row for a row op; {columns} for set_columns. */
  before: Shown | null;
  after: Shown | null;
  follows: CellChange[];
  note?: Text | null; // e.g. NUMBER_WAS_CALCULATED
  /** A Document block change: the core's word segments, old → new (Task 3). */
  segments?: Segment[];
};

export type Shown = ViewCell | Block | ViewRow | { columns: ViewColumn[] };

/** The cell a change shows, or null when it shows a block, a row or the columns. */
export const asCell = (shown: Shown | null | undefined): ViewCell | null =>
  shown && !("node" in shown) && !("cells" in shown) && ("value" in shown || "text" in shown) ? shown : null;

/** Where a comment sits, keyed on part ids and column keys (never A1 addresses). */
export type CommentAnchor =
  | { type: "cell"; row: string; column: string; moved?: boolean }
  | { type: "range"; from: { row: string; column: string }; to: { row: string; column: string }; moved?: boolean }
  | { type: "row"; row?: string; block?: string; moved?: boolean }
  | { type: "text"; block: string; start: number; end: number; quote: string; moved?: boolean }
  | { type: "deliverable"; moved?: boolean };

export type Comment = {
  id: string;
  deliverable_id: string;
  parent_id: string | null;
  kind: "note" | "review";
  anchor: CommentAnchor;
  body: string;
  author: string;
  code: "B" | "C" | null;
  check_id: string | null;
  status: "open" | "closed";
  version_n: number;
  created_at: string;
  closed_at: string | null;
  closed_by: string | null;
  fix_asked_at: string | null;
};
export type Thread = Comment & { anchor_now: CommentAnchor; replies: Comment[] };

export type Versions = {
  versions: { n: number; at: string; by: string; changes: string[] }[];
  revisions: { no: number; version_n: number; issued_at: string; signed_off: boolean }[];
};

export type CloseOut = {
  pending: number;
  open: Thread[];
  blocking: Thread[];
  check: { id: string; code: Code; checker: string; same_provider: boolean; version_n: number; at: string } | null;
  can_sign_off: boolean;
  reasons: Text[];
};

export type Segment = { op: "same" | "del" | "ins"; text: string };
export type Compare =
  | {
      rows: { id: string; change: "added" | "removed" | "moved" | "changed" | "same"; cells: Record<string, { from: ViewCell | null; to: ViewCell | null }> }[];
      total: { from: NumberCell | null; to: NumberCell | null };
    }
  | { blocks: { id: string; change: "added" | "removed" | "moved" | "changed" | "same"; segments: Segment[] }[] };

/** GET /deliverables/{d}/fill-plans, newest first. The id is for the routes only, never shown. */
export type FillPlanInfo = {
  id: string;
  file_name: string;
  created_at: string;
  /** "needs_signoff" until a Revision is signed off, then "ready". */
  status: "needs_signoff" | "ready";
};

/** GET /fill-plans/{f}/preview: what filling the client's own file would write, from the newest signed-off
 * Revision. */
export type FillPreview = {
  plan_id: string;
  deliverable_id: string;
  file_id: string;
  revision: number;
  sheet: string;
  writes: {
    cell: string;
    row: number;
    column: string;
    before: string | null;
    after: string;
    code_ours: string | null;
    code_theirs: string | null;
    client_text: string | null;
  }[];
  /** Cells left as they are: "formula" (the client's formula) or "merged". */
  skipped: { cell: string; reason: string }[];
  mismatches: { row: number; code_ours: string | null; code_theirs: string | null; accepted: boolean; text: Text }[];
  unmapped_rows: number[];
  unmapped_items: { part: string; code: string | null }[];
  accepted_mismatches: number[];
};

/** Plan 3's GET /projects/{p}/numbers/{id}/explain. */
export type Explained = {
  number: {
    id: string;
    item: { id: string; code: string | null; kind: string };
    name: string;
    value: string;
    unit: string | null;
    currency: string | null;
    dated: string | null;
    recorded_at: string;
    recorded_by: string;
    current: boolean;
    replaced_by: string | null;
    reason: string | null;
  };
  source: { id: string; kind: string; title: string; file_id: string | null; locator: Record<string, string | number>; url: string | null; dated: string | null };
  calculation: {
    id: string;
    formula: string;
    unit: string | null;
    inputs: { name: string; seq: number | null; number: string; value: string; unit: string | null; dated: string | null; source: { kind: string; title: string }; calculated: boolean }[];
    steps: { n: number; text: string; op: string; value: string; unit: string | null }[];
    stale: boolean;
    page: number;
    pages: number;
  } | null;
};

/** The core's refusal: a plain line in both languages and the field it is about. */
export type Refusal = { error: Text; field: string | null };
