// The thin adapter around react-data-grid (MIT, pinned at 7.0.0-beta.63): the only file that imports it, so AG
// Grid Community can take its place behind the same props. What the grid lacks is ours: range selection (drag,
// Shift+click, Shift+arrows mirrored in RTL), multi-cell copy and paste through the container's own copy and
// paste events (no clipboard permission), and the editor's commit. Nothing here is a portal or a fixed
// overlay, and it reads no window size, so it works inside a scaled canvas frame.
import { useImperativeHandle, useMemo, useRef, type CSSProperties, type ReactNode, type Ref } from "react";
import {
  DataGrid,
  type CellKeyboardEvent,
  type CellMouseEvent,
  type Column,
  type DataGridHandle,
  type RenderEditCellContentProps,
} from "react-data-grid";
import "react-data-grid/lib/styles.css";
import { extend, inRange, normalised, type Arrow, type Cell, type Range } from "./selection";

export type SheetColumn = {
  key: string;
  label: string;
  kind: "text" | "number" | "calc";
  edit: boolean;
  frozen: boolean;
  wrap: boolean;
  width: number;
};
export type SheetRow = { id: string; kind: "section" | "item"; level?: number };

export type GridHandle = {
  /** Brings a cell into view (the grid draws only the rows on screen). */
  scrollTo(cell: Cell): void;
  /** The cell's element, or the row's when col is left out; null when it is not drawn. */
  element(at: { row: number; col?: number }): HTMLElement | null;
};

export type GridProps<R extends SheetRow> = {
  columns: SheetColumn[]; // in screen order: frozen columns first
  rows: R[];
  direction: "rtl" | "ltr";
  rowHeight: (row: R) => number;
  renderCell: (row: R, column: SheetColumn, selected: boolean) => ReactNode;
  onCommit: (row: R, column: SheetColumn, text: string) => void;
  selection: Range | null;
  onSelection: (range: Range | null) => void;
  onCopy: (range: Range) => { text: string; html: string };
  onPaste: (at: Cell, text: string) => void;
  /** Whether a cell opens the editor, and the text it opens with. */
  canEdit: (row: R, column: SheetColumn) => boolean;
  editText: (row: R, column: SheetColumn) => string;
  /** A click on a cell, or Space on the active one (byKey): the source of a number. */
  onActivate?: (row: R, column: SheetColumn, element: HTMLElement, byKey: boolean) => void;
  /** One row pinned at the bottom: the bill total. */
  summary?: (column: SheetColumn) => ReactNode;
  label?: string;
  /** Off only in tests that need every row in the DOM. */
  virtualize?: boolean;
  ref?: Ref<GridHandle>;
};

type GridRow<R> = { row: R; draft?: string };
const ARROWS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]);
const HEADER_ROWS = 1;

// QS Mind colours on the grid's own variables; inline, so no stylesheet order can undo them.
const theme = {
  colorScheme: "light",
  "--rdg-color": "var(--color-ink)",
  "--rdg-background-color": "var(--color-paper)",
  "--rdg-header-background-color": "var(--color-stone)",
  "--rdg-border-color": "var(--color-stone)",
  "--rdg-summary-border-color": "var(--color-slate)",
  "--rdg-row-hover-background-color": "var(--color-paper)",
  "--rdg-selection-color": "var(--color-copper)",
  "--rdg-frozen-column-shadow-color": "color-mix(in srgb, var(--color-ink) 15%, transparent)",
  "--rdg-font-size": "14px",
  blockSize: "100%",
  fontFamily: "inherit",
} as CSSProperties;

function Editor<R>({
  row,
  onRowChange,
  onClose,
  text,
  wrap,
}: RenderEditCellContentProps<GridRow<R>> & { text: string; wrap: boolean }) {
  const shared = {
    autoFocus: true,
    dir: "auto" as const,
    value: row.draft ?? text,
    className: "h-full w-full bg-paper px-2 text-ink outline-2 outline-copper",
    onFocus: (event: { currentTarget: HTMLInputElement | HTMLTextAreaElement }) => event.currentTarget.select(),
    onBlur: () => onClose(true, false),
  };
  return wrap ? (
    <textarea {...shared} className={`${shared.className} resize-none py-1`} onChange={(e) => onRowChange({ ...row, draft: e.target.value })} />
  ) : (
    <input {...shared} onChange={(e) => onRowChange({ ...row, draft: e.target.value })} />
  );
}

/** The data cell under a pointer, from the grid's own ARIA indexes (no coordinates, so a scaled frame is fine). */
function cellAt(target: EventTarget | null, rowCount: number): Cell | null {
  const el = target instanceof Element ? target.closest('[role="gridcell"]') : null;
  const rowEl = el?.closest('[role="row"]');
  if (!el || !rowEl) return null;
  const row = Number(rowEl.getAttribute("aria-rowindex")) - HEADER_ROWS - 1;
  const col = Number(el.getAttribute("aria-colindex")) - 1;
  return row >= 0 && row < rowCount && col >= 0 ? { row, col } : null;
}

export function Grid<R extends SheetRow>(props: GridProps<R>) {
  const { columns, rows, direction, selection, onSelection, renderCell, canEdit, editText, summary } = props;
  const grid = useRef<DataGridHandle>(null);
  const dragging = useRef<Cell | null>(null);
  const size = { rows: rows.length, cols: columns.length };

  const handle: GridHandle = {
    scrollTo: (cell) => grid.current?.scrollToCell({ rowIdx: cell.row, idx: cell.col }),
    element: ({ row, col }) => {
      const rowEl = grid.current?.element?.querySelector<HTMLElement>(
        `[role="row"][aria-rowindex="${row + HEADER_ROWS + 1}"]`,
      );
      if (!rowEl || col === undefined) return rowEl ?? null;
      return rowEl.querySelector<HTMLElement>(`[role="gridcell"][aria-colindex="${col + 1}"]`);
    },
  };
  useImperativeHandle(props.ref, () => handle);

  const gridRows = useMemo<GridRow<R>[]>(() => rows.map((row) => ({ row })), [rows]);

  const gridColumns = useMemo<Column<GridRow<R>, unknown>[]>(
    () =>
      columns.map((column, col) => ({
        key: column.key,
        name: column.label,
        width: column.width,
        minWidth: 40,
        frozen: column.frozen,
        editable: (g: GridRow<R>) => canEdit(g.row, column),
        renderCell: ({ row: g, rowIdx }) => {
          const selected = inRange(selection, rowIdx, col);
          return (
            <div
              className={`-mx-2 flex h-full items-center px-2 ${selected ? "bg-copper/10" : ""}`}
              data-selected={selected || undefined}
            >
              {renderCell(g.row, column, selected)}
            </div>
          );
        },
        renderEditCell: (p) => <Editor {...p} text={editText(p.row.row, column)} wrap={column.wrap} />,
        ...(summary ? { renderSummaryCell: () => summary(column) } : {}),
      })),
    [columns, selection, renderCell, canEdit, editText, summary],
  );

  function onCellMouseDown({ rowIdx, column }: { rowIdx: number; column: { idx: number } }, event: CellMouseEvent) {
    if (event.button !== 0) return;
    const cell = { row: rowIdx, col: column.idx };
    if (event.shiftKey && selection) {
      event.preventGridDefault(); // the active cell stays at the anchor
      onSelection({ anchor: selection.anchor, focus: cell });
      return;
    }
    dragging.current = cell;
    onSelection({ anchor: cell, focus: cell });
    const stop = () => {
      dragging.current = null;
      window.removeEventListener("mouseup", stop);
    };
    window.addEventListener("mouseup", stop);
  }

  function onCellKeyDown(
    args: { mode: "ACTIVE" | "EDIT"; rowIdx: number; column?: { idx: number } | undefined; row?: GridRow<R> },
    event: CellKeyboardEvent,
  ) {
    if (args.mode !== "ACTIVE" || !args.column) return;
    const here = { row: args.rowIdx, col: args.column.idx };
    if (event.shiftKey && ARROWS.has(event.key)) {
      event.preventGridDefault();
      event.preventDefault();
      const next = extend(selection ?? { anchor: here, focus: here }, event.key as Arrow, direction, size);
      onSelection(next);
      handle.scrollTo(next.focus);
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") {
      event.preventGridDefault(); // no editor: the paste event below takes the whole block
    } else if (event.key === " " && !event.shiftKey && !event.ctrlKey && !event.metaKey && props.onActivate && args.row) {
      const column = columns[here.col];
      const el = (event.target as Element).closest<HTMLElement>('[role="gridcell"]');
      if (column && el) {
        event.preventGridDefault();
        event.preventDefault();
        props.onActivate(args.row.row, column, el, true);
      }
    }
  }

  const editing = (target: EventTarget) => target instanceof Element && target.matches("input, textarea");

  return (
    <div
      className="h-full"
      onMouseOver={(event) => {
        if (!dragging.current || (event.buttons & 1) === 0) return;
        const cell = cellAt(event.target, rows.length);
        if (cell && selection && (cell.row !== selection.focus.row || cell.col !== selection.focus.col))
          onSelection({ anchor: dragging.current, focus: cell });
      }}
      onCopy={(event) => {
        if (editing(event.target) || !selection) return;
        const { text, html } = props.onCopy(selection);
        event.clipboardData.setData("text/plain", text);
        event.clipboardData.setData("text/html", html);
        event.preventDefault();
      }}
      onPaste={(event) => {
        if (editing(event.target) || !selection) return;
        const { top, start } = normalised(selection);
        event.preventDefault();
        props.onPaste({ row: top, col: start }, event.clipboardData.getData("text/plain"));
      }}
    >
      <DataGrid<GridRow<R>, unknown, string>
        ref={grid}
        aria-label={props.label}
        columns={gridColumns}
        rows={gridRows}
        rowKeyGetter={(g) => g.row.id}
        rowHeight={(g) => props.rowHeight(g.row)}
        headerRowHeight={36}
        direction={direction}
        enableVirtualization={props.virtualize ?? true}
        bottomSummaryRows={summary ? [{}] : undefined}
        style={theme}
        rowClass={(g) => (g.row.kind === "section" ? "bg-stone/60" : undefined)}
        onCellMouseDown={onCellMouseDown}
        onCellClick={({ row, column }, event) => {
          const target = columns[column.idx];
          const el = (event.target as Element).closest<HTMLElement>('[role="gridcell"]');
          if (target && el && props.onActivate) props.onActivate(row.row, target, el, false);
        }}
        onCellKeyDown={onCellKeyDown}
        onActivePositionChange={({ rowIdx, row, column }) => {
          if (dragging.current) return;
          if (!row || !column) return;
          const cell = { row: rowIdx, col: column.idx };
          onSelection({ anchor: cell, focus: cell });
        }}
        onRowsChange={(updated, { indexes, column }) => {
          const index = indexes[0];
          const g = index === undefined ? undefined : updated[index];
          const target = columns[column.idx];
          if (g?.draft !== undefined && target) props.onCommit(g.row, target, g.draft);
        }}
      />
    </div>
  );
}
