// What one sheet cell shows: its value, a Suggested change (the new value in Copper over the old one struck in Slate,
// ✓ ✗), a value the QS Calc Engine would recalculate, comment marks, and a section's fold button. Values are never
// computed here. The change the engineer moves to in the review reveals its new value (220 ms; at once with reduced
// motion).
import { useLayoutEffect, useRef } from "react";
import type { Change, Thread, ViewCell, ViewColumn, ViewRow } from "../../deliverables/types";
import { asCell, isNumber } from "../../deliverables/types";
import { pick, t } from "../../i18n";
import { sourceLineHandlers } from "../../sources/line";
import { TARGET } from "../../sources/targets";
import { DUR, play } from "../../ui/motion";
import { fieldKey, numberName } from "./clipboard";
import { formatDecimal } from "./format";

export const cellKey = (row: string, column: string) => `${row}\u0000${column}`;

export type Pending = { change: Change; before: ViewCell | null; after: ViewCell | null; recalculated: boolean };
export type Mark = "review" | "note";

/** A change's new value coming in where it shows: up a little and fading in (whole values, never by letter). */
export const REVEAL: Keyframe[] = [
  { opacity: 0, transform: "translateY(3px)" },
  { opacity: 1, transform: "none" },
];

/** The cells each pending change paints. An edit wins over a recalculation shown on the same cell. */
export function pendingCells(changes: Change[], columns: ViewColumn[], titleColumn: string | undefined) {
  const cells = new Map<string, Pending>();
  const put = (row: string | null, column: string | undefined, p: Omit<Pending, "recalculated">, recalculated: boolean) => {
    const key = row !== null && column && cellKey(row, column);
    if (key && !(recalculated && cells.has(key))) cells.set(key, { ...p, recalculated });
  };
  const pending = changes.filter((c) => c.status === "pending");
  for (const change of pending) {
    const { op } = change;
    const [before, after] = [asCell(change.before), asCell(change.after)];
    if (op.op === "set_number")
      put(op.row, columns.find((c) => c.kind === "number" && numberName(c) === op.name)?.key, { change, before, after }, false);
    else if (op.op === "set_field")
      put(op.row, columns.find((c) => c.kind === "text" && fieldKey(c) === op.key)?.key, { change, before, after }, false);
    else if (op.op === "set_section_title") put(op.row, titleColumn, { change, before, after }, false);
    else if (op.op === "update_from_records")
      for (const cell of op.cells) put(cell.row, cell.column, { change, before: cell.before, after: cell.after }, false);
  }
  for (const change of pending)
    for (const f of change.follows) put(f.row, f.column, { change, before: f.before, after: f.after }, true);
  return cells;
}

/** Open comments by cell: a range marks its first cell, a row its first column. */
export function commentMarks(threads: Thread[], columns: ViewColumn[]) {
  const marks = new Map<string, Set<Mark>>();
  const first = columns[0]?.key;
  for (const thread of threads) {
    if (thread.status !== "open") continue;
    const a = thread.anchor_now ?? thread.anchor;
    const key =
      a.type === "cell"
        ? cellKey(a.row, a.column)
        : a.type === "range"
          ? cellKey(a.from.row, a.from.column)
          : a.type === "row" && a.row && first
            ? cellKey(a.row, first)
            : undefined;
    if (!key) continue;
    marks.set(key, new Set([...(marks.get(key) ?? []), thread.kind]));
  }
  return marks;
}

export function Value({ cell }: { cell: ViewCell | null | undefined }) {
  if (!cell) return null;
  if (isNumber(cell)) return <bdi dir="ltr">{formatDecimal(cell.value, cell.currency ? 2 : undefined)}</bdi>;
  return <span dir="auto">{cell.text}</span>;
}

function Marks({ marks }: { marks: Set<Mark> | undefined }) {
  if (!marks) return null;
  return (
    <span className="absolute end-1 top-1 flex gap-0.5">
      {marks.has("review") && (
        <span className="size-2 rounded-full bg-copper" title={t("reviewComment")}>
          <span className="sr-only">{t("reviewComment")}</span>
        </span>
      )}
      {marks.has("note") && (
        <span className="size-2 rounded-full border border-slate" title={t("reviewNote")}>
          <span className="sr-only">{t("reviewNote")}</span>
        </span>
      )}
    </span>
  );
}

function Suggested({
  pending,
  end,
  current,
  onAccept,
  onReject,
  tabIndex = -1,
}: {
  pending: Pending;
  end: boolean;
  current: boolean;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  tabIndex?: number;
}) {
  const value = useRef<HTMLModElement>(null);
  useLayoutEffect(() => {
    if (current && value.current) void play(value.current, REVEAL, DUR.base);
  }, [current]);
  const stop = (fn: () => void) => (event: { stopPropagation(): void }) => {
    event.stopPropagation(); // not a click on the cell: no source popover
    fn();
  };
  return (
    <span className={`flex w-full flex-col leading-snug ${end ? "items-end text-end" : "items-start"}`}>
      <span className="flex items-center gap-1">
        <ins ref={value} className="inline-block font-semibold text-copper no-underline">
          <Value cell={pending.after} />
        </ins>
        {pending.recalculated ? (
          <span className="text-xs text-slate">{t("sheetRecalculated")}</span>
        ) : (
          <>
            <button
              type="button"
              tabIndex={tabIndex}
              aria-label={t("sheetAccept")}
              title={t("sheetAccept")}
              className="rounded px-1 text-ink hover:bg-stone"
              onMouseDown={(e) => e.stopPropagation()}
              onClick={stop(() => onAccept(pending.change.id))}
            >
              <span aria-hidden>✓</span>
            </button>
            <button
              type="button"
              tabIndex={tabIndex}
              aria-label={t("sheetReject")}
              title={t("sheetReject")}
              className="rounded px-1 text-copper hover:bg-stone"
              onMouseDown={(e) => e.stopPropagation()}
              onClick={stop(() => onReject(pending.change.id))}
            >
              <span aria-hidden>✗</span>
            </button>
          </>
        )}
      </span>
      {pending.before && (
        <del className="text-slate">
          <Value cell={pending.before} />
        </del>
      )}
    </span>
  );
}

export type CellProps = {
  row: ViewRow;
  column: ViewColumn;
  titleColumn: string | undefined;
  direction: "rtl" | "ltr";
  pending: Pending | undefined;
  /** The change the engineer is on in the review. */
  current?: boolean;
  marks: Set<Mark> | undefined;
  collapsed: boolean;
  onToggle: (sectionId: string) => void;
  onAccept: (changeId: string) => void;
  onReject: (changeId: string) => void;
  /** Where the number's source shows (../../sources/targets.ts): hovering it draws the source line. */
  sourceKeys?: string[];
  /** Its source card is open: the cell is outlined 2 px in Ink. */
  open?: boolean;
  /** The grid's for the cell's buttons: reachable by Tab only on the active cell (the arrows move between cells). */
  tabIndex?: number;
};

export function SheetCell(p: CellProps) {
  const { row, column } = p;
  const cell = row.cells[column.key];
  const number = column.kind !== "text" || isNumber(cell);
  const wrap = column.wrap ? "whitespace-normal break-words" : "truncate";
  let content;
  if (p.pending) {
    content = <Suggested pending={p.pending} end={number} current={!!p.current} onAccept={p.onAccept} onReject={p.onReject} tabIndex={p.tabIndex} />;
  } else if (row.kind === "section" && column.key === p.titleColumn) {
    content = (
      <span dir="auto" className={`font-bold ${wrap}`}>
        {row.title}
      </span>
    );
  } else if (column.from === "code" || (column.from === undefined && column.key === "code")) {
    content =
      row.kind === "section" ? (
        <FoldButton {...p} />
      ) : (
        <>
          <bdi className="truncate">{row.code}</bdi>
          {row.problem && (
            <span role="img" aria-label={pick(row.problem)} title={pick(row.problem)} className="ms-1 shrink-0 font-bold text-copper">
              !
            </span>
          )}
        </>
      );
  } else if (isNumber(cell)) {
    content = (
      // the ledger number shows here: a number quoted elsewhere draws its source line to this cell
      <span
        className={`w-full text-end ${p.open ? "rounded-[4px] outline-2 outline-ink" : ""}`}
        {...(cell.number_id ? { [TARGET]: `number:${cell.number_id}` } : {})}
        {...sourceLineHandlers(p.sourceKeys ?? [])}
      >
        <Value cell={cell} />
      </span>
    );
  } else if (!cell && row.kind === "section" && column.kind === "calc") {
    content = <span className="w-full text-end text-slate">—</span>; // nothing priced under it yet: never 0
  } else if (cell) {
    content = column.wrap ? (
      <span dir="auto" className={wrap}>
        {cell.text}
      </span>
    ) : (
      <bdi className="truncate">{cell.text}</bdi>
    );
  }
  return (
    <>
      {content}
      <Marks marks={p.marks} />
    </>
  );
}

function FoldButton({ row, collapsed, direction, onToggle, tabIndex = -1 }: CellProps) {
  const chevron = collapsed ? (direction === "rtl" ? "◂" : "▸") : "▾";
  const label = collapsed ? t("sheetExpand") : t("sheetCollapse");
  return (
    <button
      type="button"
      tabIndex={tabIndex}
      aria-expanded={!collapsed}
      aria-label={`${label}: ${row.title ?? ""}`}
      title={label}
      className="rounded px-1 text-slate hover:bg-stone hover:text-ink"
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onToggle(row.id);
      }}
    >
      <span aria-hidden>{chevron}</span>
    </button>
  );
}

/** Names a cell in a plain-words list: «03/02 الفئة». */
export function cellName(row: ViewRow, column: ViewColumn, language: "ar" | "en"): string {
  return `${row.code ?? row.title ?? ""} ${column.label[language]}`.trim();
}
