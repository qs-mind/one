// The Sheet viewer: a Deliverable's priced BOQ as the core's view draws it. Its direction comes from the
// Deliverable's language, not the screen's. Every edit, typed or pasted, is sent as a Suggested change and
// shows old → new with ✓ ✗ until the engineer decides; nothing on this screen adds, multiplies or totals.
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type CSSProperties, type Ref } from "react";
import { deliverablesApi, type Accepted, type Rejected } from "../../deliverables/api";
import type { Change, NumberCell, Op, SheetView, Thread, ViewRow } from "../../deliverables/types";
import { isNumber } from "../../deliverables/types";
import { count, dir, fill, language, pick, t, texts, useLanguage, type Text } from "../../i18n";
import { RollingNumber } from "../../ui/RollingNumber";
import { cellText, pasteOps, parseTsv, toHtml, toTsv, why } from "./clipboard";
import { cellKey, cellName, commentMarks, pendingCells, SheetCell } from "./cells";
import { formatDecimal } from "./format";
import { loadCollapsed, saveCollapsed, visibleRows } from "./collapse";
import { Grid, type GridHandle, type SheetColumn } from "./grid";
import { linesHeight, makeMeasure, oneLineWidth, rowHeight, shownWidth, titleColumnOf } from "./heights";
import { normalised, type Cell, type Range } from "./selection";
import { SourcePopover } from "./SourcePopover";
import { hideSourceLine, showSourceLine } from "../../sources/line";
import { sourceKeys } from "../../sources/targets";

/** A cell or row as the viewer finds it: part id and column key (Plan 7's anchor, its sheet fields). */
export type SheetAnchor = { row?: string; column?: string };
export type SheetRange = { from: { row: string; column: string }; to: { row: string; column: string } };
export type SheetHandle = {
  /** The cell's (or row's) box in the viewer's own unscaled pixels, or null when it is not on screen. */
  locate(anchor: SheetAnchor): DOMRect | null;
};

export type SheetViewerProps = {
  projectId: string;
  view: SheetView;
  /** Pending changes and comment threads, as the core lists them. */
  changes?: Change[];
  comments?: Thread[];
  mode?: "frame" | "full";
  /** After a change is sent, accepted or rejected: the owner refetches the view and the changes. */
  onChanged?: () => void;
  onSelection?: (range: SheetRange | null) => void;
  onToggleFullScreen?: () => void;
  /** Whether the board is full screen now, for the toggle's words; left out, the full review mode counts as it. */
  fullScreen?: boolean;
  virtualize?: boolean;
  /** A document that is not ours (the client's BOQ): nothing can be typed, pasted or changed. */
  readOnly?: boolean;
  /** The review board's change review: while `active`, the rows with no change dim; `current` is the change the
   * engineer is on. Left out (a frame), nothing dims. */
  review?: { active: boolean; current: string | null };
  /** After an accept from a cell: its answer, with its Undo when it has one. */
  onAccepted?: (answer: Accepted) => void;
  /** After a reject from a cell: its answer, with its Undo. */
  onRejected?: (answer: Rejected) => void;
  ref?: Ref<SheetHandle>;
};

const NONE: never[] = [];
/** Room kept for a scroll bar, in px. */
const SCROLLBAR = 16;
/** The narrowest the description gets when the board gives the columns less room than they ask (as set, px). */
const TITLE_MIN = 240;
/** The grid's header row and its total row, in px (react-data-grid's summary row with a row-height function). */
const HEADER_H = 44;
const TOTAL_H = 35;

/** The status chips with text labels (never colour alone); the Document viewer shows the same. */
/** The Deliverable's chips. With `status` false the status itself is left out: a frame's strip already says it. */
export function StatusChips({ view, status: withStatus = true }: { view: Pick<SheetView, "status" | "code" | "same_provider" | "off_desk">; status?: boolean }) {
  const status =
    view.status === "signed_off"
      ? t("statusSignedOff")
      : view.status === "checked"
        ? fill(t("statusChecked"), { code: view.code ?? "" })
        : t("statusDraft");
  const chip = "rounded-full border px-2.5 text-xs leading-6";
  return (
    <>
      {withStatus && <span className={`${chip} ${view.code === "C" ? "border-copper text-copper" : "border-slate text-ink"}`}>{status}</span>}
      {view.same_provider && <span className={`${chip} border-slate text-slate`}>{t("statusSameProvider")}</span>}
      {view.off_desk && <span className={`${chip} border-slate text-slate`}>{t("statusOffDesk")}</span>}
    </>
  );
}

export function SheetViewer(props: SheetViewerProps) {
  const { projectId, view, changes = NONE, comments = NONE, onChanged } = props;
  useLanguage();
  const direction = dir(view.language);
  const root = useRef<HTMLDivElement>(null);
  const grid = useRef<GridHandle>(null);

  const full = props.mode === "full";
  // In full mode the sheet fills the board's width: the room the columns leave goes to the description, so no empty
  // band sits beside the last column (the rows then need fewer lines). In a frame the columns keep their widths.
  const gridBox = useRef<HTMLDivElement>(null);
  const [room, setRoom] = useState(0);
  useEffect(() => {
    const el = gridBox.current;
    if (!full || !el || typeof ResizeObserver === "undefined") return;
    const sizes = new ResizeObserver(() => setRoom(el.clientWidth));
    sizes.observe(el);
    setRoom(el.clientWidth);
    return () => sizes.disconnect();
  }, [full]);

  // Row heights and one-line widths in the real font once it has loaded.
  const measure = useMemo(makeMeasure, []);
  const [fontsLoaded, setFontsLoaded] = useState(0);
  useEffect(() => {
    let live = true;
    void document.fonts?.ready.then(() => live && setFontsLoaded((n) => n + 1));
    return () => {
      live = false;
    };
  }, []);

  // Frozen columns first: react-data-grid moves them to the start edge, so screen order matches indexes. A one-line
  // column is as wide as its longest value (a code is never cut). In full mode the description takes what the board
  // has left, or gives room back down to TITLE_MIN so every column fits; only past that does the grid scroll.
  const columns = useMemo(() => {
    void fontsLoaded;
    const totalText = view.total ? [formatDecimal(view.total.value, view.total.currency ? 2 : undefined)] : [];
    const ordered = [...view.columns.filter((c) => c.frozen), ...view.columns.filter((c) => !c.frozen)].map((c) => ({
      ...c,
      width: oneLineWidth(c, pick(c.label, view.language), view.rows, measure, c.kind === "calc" ? totalText : []),
    }));
    const title = titleColumnOf(ordered);
    const extra = room - ordered.reduce((sum, c) => sum + shownWidth(c.width), 0) - SCROLLBAR;
    if (!full || !title || room <= 0 || extra === 0) return ordered;
    return ordered.map((c) => (c.key === title ? { ...c, width: Math.max(c.width + extra, Math.min(c.width, TITLE_MIN)) } : c));
  }, [view.columns, view.rows, view.total, view.language, full, room, measure, fontsLoaded]);
  const byKey = useMemo(() => new Map(columns.map((c) => [c.key, c])), [columns]);
  const titleColumn = titleColumnOf(columns);
  const gridColumns = useMemo<SheetColumn[]>(
    () => columns.map(({ from: _, label, ...c }) => ({ ...c, label: pick(label, view.language) })),
    [columns, view.language],
  );

  const [collapsed, setCollapsed] = useState(() => loadCollapsed(view.id));
  useEffect(() => setCollapsed(loadCollapsed(view.id)), [view.id]);
  const rows = useMemo(() => visibleRows(view.rows, collapsed), [view.rows, collapsed]);
  function toggle(sectionId: string) {
    const next = new Set(collapsed);
    if (!next.delete(sectionId)) next.add(sectionId);
    setCollapsed(next);
    saveCollapsed(view.id, next);
  }

  // Changes sent from here show at once; the owner's next list replaces them.
  const [posted, setPosted] = useState<Change[]>([]);
  const [decided, setDecided] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => {
    setPosted([]);
    setDecided(new Set());
  }, [changes, view.version]);
  const allChanges = useMemo(() => {
    const ids = new Set(changes.map((c) => c.id));
    return [...changes, ...posted.filter((c) => !ids.has(c.id))].filter((c) => !decided.has(c.id));
  }, [changes, posted, decided]);
  const pending = useMemo(() => pendingCells(allChanges, columns, titleColumn), [allChanges, columns, titleColumn]);
  // The rows a pending change paints or is about (a row it removes or moves): they stay clear while reviewing
  const changedRows = useMemo(() => {
    const ids = new Set([...pending.keys()].map((k) => k.split("\u0000")[0]!));
    for (const change of allChanges) {
      const row = (change.op as { row?: string }).row;
      if (change.status === "pending" && row) ids.add(row);
    }
    return ids;
  }, [pending, allChanges]);
  const reviewing = !!props.review?.active && changedRows.size > 0;
  const rowClass = useCallback(
    (row: ViewRow) => (reviewing && !changedRows.has(row.id) ? "review-dim" : undefined),
    [reviewing, changedRows],
  );
  const marks = useMemo(() => commentMarks(comments, columns), [comments, columns]);

  // a row with a Suggested change holds two lines
  const heights = useMemo(() => {
    void fontsLoaded;
    const changed = new Set([...pending.keys()].map((k) => k.split("\u0000")[0]));
    return new Map(
      rows.map((r) => [r.id, Math.max(rowHeight(r, columns, measure), changed.has(r.id) ? linesHeight(2) : 0)]),
    );
  }, [rows, columns, measure, pending, fontsLoaded]);
  const contentHeight =
    HEADER_H + [...heights.values()].reduce((sum, h) => sum + h, 0) + (view.total ? TOTAL_H : 0) + SCROLLBAR;

  const [selection, setSelection] = useState<Range | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [popover, setPopover] = useState<{
    cell: NumberCell;
    style: CSSProperties;
    from: HTMLElement;
    focus: boolean;
    label: string;
  } | null>(null);
  function select(range: Range | null) {
    setSelection(range);
    setPopover(null); // a source belongs to the cell it was opened on
  }

  // Where a number's source shows on screen: its file's frame, page or row (the sheet's own cells are not sources).
  const keysOf = useCallback(
    (cell: NumberCell) => {
      const source = cell.source !== null ? view.sources[cell.source] : undefined;
      return source ? sourceKeys({ fileId: source.file_id, locator: source.locator, sourceId: cell.source }) : [];
    },
    [view.sources],
  );

  // A number focused from the keyboard draws its source line, as hovering it does
  useEffect(() => {
    if (!selection || selection.anchor.row !== selection.focus.row || selection.anchor.col !== selection.focus.col) return;
    const [r, c] = [rows[selection.focus.row], columns[selection.focus.col]];
    const cell = r && c ? r.cells[c.key] : undefined;
    const el = grid.current?.element({ row: selection.focus.row, col: selection.focus.col });
    // a click under the pointer already drew it from the number itself
    if (!isNumber(cell) || !el || el.matches(":hover") || !root.current?.contains(document.activeElement)) return;
    showSourceLine(el, keysOf(cell));
    return () => hideSourceLine(el);
  }, [selection, rows, columns, keysOf]);

  // Reported when the range moves, not when the owner re-renders with a new callback.
  const onSelection = useRef(props.onSelection);
  onSelection.current = props.onSelection;
  useEffect(() => {
    const report = onSelection.current;
    if (!report) return;
    if (!selection) return report(null);
    const { top, bottom, start, end } = normalised(selection);
    const [a, b, c, d] = [rows[top], rows[bottom], columns[start], columns[end]];
    report(a && b && c && d ? { from: { row: a.id, column: c.key }, to: { row: b.id, column: d.key } } : null);
  }, [selection, rows, columns]);

  /** A box inside the viewer, in its own unscaled pixels (the viewer may sit in a CSS-scaled canvas frame). */
  function boxOf(el: HTMLElement): DOMRect | null {
    const box = root.current;
    if (!box) return null;
    const outer = box.getBoundingClientRect();
    const inner = el.getBoundingClientRect();
    const scale = box.offsetWidth ? outer.width / box.offsetWidth || 1 : 1;
    return new DOMRect(
      (inner.left - outer.left) / scale,
      (inner.top - outer.top) / scale,
      inner.width / scale,
      inner.height / scale,
    );
  }

  useImperativeHandle(props.ref, () => ({
    locate({ row, column }) {
      const r = rows.findIndex((x) => x.id === row);
      const c = column === undefined ? undefined : columns.findIndex((x) => x.key === column);
      if (r < 0 || c === -1) return null;
      grid.current?.scrollTo({ row: r, col: c ?? 0 });
      const el = grid.current?.element({ row: r, col: c });
      return el ? boxOf(el) : null;
    },
  }));

  const say = (line: Text) => setNotice(pick(line));

  async function propose(ops: Op[]) {
    if (ops.length === 0) return;
    const answer = await deliverablesApi.propose(projectId, view.id, ops);
    if (!answer.ok) return say(answer.error);
    setPosted((list) => [...list, ...answer.data.changes]);
    onChanged?.();
  }

  async function decide(changeId: string, accept: boolean) {
    const answer = accept
      ? await deliverablesApi.accept(projectId, view.id, { ids: [changeId] })
      : await deliverablesApi.reject(projectId, view.id, [changeId]);
    if (!answer.ok) return say(answer.error);
    setDecided((ids) => new Set([...ids, changeId]));
    if (accept) props.onAccepted?.(answer.data as Accepted);
    else props.onRejected?.(answer.data as Rejected);
    onChanged?.();
  }

  function sendBlock(at: Cell, block: string[][]) {
    const { ops, refused } = pasteOps(at, block, rows, columns);
    const lang = language();
    const groups = new Map<Text, string[]>();
    for (const { cell, why: reason } of refused) {
      const r = rows[cell.row];
      const c = columns[cell.col];
      if (r && c) groups.set(reason, [...(groups.get(reason) ?? []), cellName(r, c, view.language)]);
    }
    const lines = [...groups].map(([reason, cells]) =>
      fill(t("sheetPasteRefused"), { cells: cells.join(lang === "ar" ? "، " : ", "), why: pick(reason) }),
    );
    setNotice(lines.length ? lines.join(" ") : null);
    void propose(ops);
  }

  function openSource(cell: NumberCell, el: HTMLElement, focus: boolean, label: string) {
    const box = boxOf(el);
    const width = root.current?.offsetWidth ?? 0;
    if (!box) return;
    // Placed under the cell, lined up with its start edge (the right edge in RTL).
    const side = direction === "rtl" ? { right: Math.max(width - box.right, 0) } : { left: box.left };
    setPopover({ cell, style: { top: box.bottom, ...side }, from: el, focus, label });
  }

  function closeSource() {
    popover?.from.focus();
    setPopover(null);
  }

  const current = props.review?.current ?? null;
  const renderCell = useCallback(
    (row: ViewRow, column: SheetColumn, _selected: boolean, tabIndex: number) => {
      const vc = byKey.get(column.key)!;
      return (
        <SheetCell
          tabIndex={tabIndex}
          row={row}
          column={vc}
          titleColumn={titleColumn}
          direction={direction}
          pending={pending.get(cellKey(row.id, column.key))}
          current={!!current && pending.get(cellKey(row.id, column.key))?.change.id === current}
          marks={marks.get(cellKey(row.id, column.key))}
          collapsed={collapsed.has(row.id)}
          open={!!popover && popover.cell === row.cells[column.key]}
          onToggle={toggle}
          onAccept={(id) => void decide(id, true)}
          onReject={(id) => void decide(id, false)}
          sourceKeys={isNumber(row.cells[column.key]) ? keysOf(row.cells[column.key] as NumberCell) : undefined}
        />
      );
    },
    // toggle and decide read the latest state when called
    [byKey, titleColumn, direction, pending, marks, collapsed, keysOf, current, popover],
  );
  const readOnly = !!props.readOnly;
  const canEdit = useCallback(
    (row: ViewRow, column: SheetColumn) => !readOnly && why(row, byKey.get(column.key)!, titleColumn) === null,
    [byKey, titleColumn, readOnly],
  );
  const editText = useCallback(
    (row: ViewRow, column: SheetColumn) => cellText(row, byKey.get(column.key)!, titleColumn),
    [byKey, titleColumn],
  );
  const total = view.total;
  const totalColumn = columns.find((c) => c.kind === "calc")?.key;
  const summary = useCallback(
    (column: SheetColumn, tabIndex: number) => {
      if (column.key === titleColumn)
        return (
          <span dir="auto" className="font-bold">
            {pick(texts.sheetTotal, view.language)}
          </span>
        );
      if (column.key !== totalColumn || !total) return null;
      return (
        <button
          type="button"
          tabIndex={tabIndex}
          className="w-full text-end font-bold hover:text-copper"
          onClick={(event) => openSource(total, event.currentTarget, event.detail === 0, pick(texts.sheetTotal, view.language))}
        >
          {/* the core's total, rolling to its new value when an edit changes it; another Deliverable's shows still */}
          <bdi dir="ltr">
            <RollingNumber key={view.id} text={formatDecimal(total.value, total.currency ? 2 : undefined)} />
          </bdi>
        </button>
      );
    },
    // openSource reads the layout when called
    [titleColumn, totalColumn, total, view.language, view.id],
  );

  // in a frame, the frame's strip already says the client's document is read only: it is not said twice, and the
  // header, with nothing left to show, keeps only the title for screen readers
  const badge = readOnly && props.mode !== "frame";
  const shown = !readOnly || badge || full || !!props.onToggleFullScreen;
  return (
    <div
      ref={root}
      className="relative flex h-full min-h-0 flex-col bg-paper text-ink"
      onKeyDown={(event) => {
        if (event.key === "Escape" && popover) closeSource();
      }}
      onFocus={(event) => {
        if (popover && event.target.matches("input, textarea")) setPopover(null); // the cell editor opened
      }}
    >
      <header className={shown ? "flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3" : "sr-only"}>
        {/* in a frame, the frame's strip shows the title: here it is only said, not shown twice */}
        <h2 dir="auto" className={full ? "text-lg font-semibold" : "sr-only"}>
          {view.title}
        </h2>
        {readOnly ? (
          badge && <span className="rounded-full border border-slate px-2.5 text-xs leading-6 text-slate">{t("clientBoqReadOnly")}</span>
        ) : (
          <>
            <StatusChips view={view} status={props.mode !== "frame"} />
            <span className="text-slate">{fill(t("reviewVersion"), { n: view.version })}</span>
            {view.revision && <span className="text-slate">{fill(t("reviewRev"), { n: view.revision.no })}</span>}
            {view.pending > 0 && <span>{count("sheetPending", view.pending)}</span>}
          </>
        )}
        {props.onToggleFullScreen && (
          <button
            type="button"
            aria-pressed={props.fullScreen ?? full}
            className="ms-auto rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
            onClick={props.onToggleFullScreen}
          >
            {(props.fullScreen ?? full) ? t("sheetLeaveFullScreen") : t("sheetFullScreen")}
          </button>
        )}
      </header>
      {view.sample && (
        <p role="note" className="bg-stone px-5 py-2 text-ink">
          {t("sheetSample")}
        </p>
      )}
      {notice && (
        <p role="alert" className="flex items-start justify-between gap-3 px-5 py-2 text-copper">
          <span>{notice}</span>
          <button type="button" className="rounded px-2 text-ink hover:bg-stone" onClick={() => setNotice(null)}>
            {t("close")}
          </button>
        </p>
      )}
      <div
        ref={gridBox}
        lang={view.language}
        // in full mode the grid is as tall as its rows (and no taller than its room), so a short bill leaves no empty
        // band above its total: the review panels under it take the room
        className={`${full ? "min-h-0 flex-[0_1_auto]" : "min-h-0 flex-1"}${props.review ? " sheet-review" : ""}`}
        style={full ? { height: contentHeight } : undefined}
      >
        <Grid<ViewRow>
          ref={grid}
          label={view.title}
          columns={gridColumns}
          rows={rows}
          direction={direction}
          rowHeight={(row) => heights.get(row.id) ?? linesHeight(1)}
          rowClass={props.review ? rowClass : undefined}
          renderCell={renderCell}
          canEdit={canEdit}
          editText={editText}
          onCommit={(row, column, text) => {
            const r = rows.indexOf(row);
            const c = columns.findIndex((x) => x.key === column.key);
            if (r >= 0 && c >= 0 && !readOnly) sendBlock({ row: r, col: c }, [[text]]);
          }}
          selection={selection}
          onSelection={select}
          onCopy={(range) => {
            const { top, bottom, start, end } = normalised(range);
            const values = rows
              .slice(top, bottom + 1)
              .map((r) => columns.slice(start, end + 1).map((c) => cellText(r, c, titleColumn)));
            return { text: toTsv(values), html: toHtml(values, direction) };
          }}
          onPaste={(at, text) => !readOnly && sendBlock(at, parseTsv(text))}
          onActivate={(row, column, el, byKey) => {
            const cell = row.cells[column.key];
            if (isNumber(cell) && !pending.has(cellKey(row.id, column.key))) openSource(cell, el, byKey, column.label);
          }}
          summary={total ? summary : undefined}
          virtualize={props.virtualize}
        />
      </div>
      {popover && (
        <SourcePopover
          projectId={projectId}
          cell={popover.cell}
          sources={view.sources}
          style={popover.style}
          focus={popover.focus}
          from={popover.from}
          label={popover.label}
          onClose={closeSource}
        />
      )}
    </div>
  );
}
