// The Sheet viewer: a Deliverable's priced BOQ as the core's view draws it. Its direction comes from the
// Deliverable's language, not the screen's. Every edit, typed or pasted, is sent as a Suggested change and
// shows old → new with ✓ ✗ until the engineer decides; nothing on this screen adds, multiplies or totals.
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type CSSProperties, type Ref } from "react";
import { deliverablesApi } from "../../deliverables/api";
import type { Change, NumberCell, Op, SheetView, Thread, ViewRow } from "../../deliverables/types";
import { isNumber } from "../../deliverables/types";
import { dir, fill, language, pick, t, texts, useLanguage, type Text } from "../../i18n";
import { cellText, pasteOps, parseTsv, toHtml, toTsv, why } from "./clipboard";
import { cellKey, cellName, commentMarks, pendingCells, SheetCell, Value } from "./cells";
import { loadCollapsed, saveCollapsed, visibleRows } from "./collapse";
import { Grid, type GridHandle, type SheetColumn } from "./grid";
import { linesHeight, makeMeasure, rowHeight, titleColumnOf } from "./heights";
import { normalised, type Cell, type Range } from "./selection";
import { SourcePopover } from "./SourcePopover";

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
  virtualize?: boolean;
  ref?: Ref<SheetHandle>;
};

const NONE: never[] = [];

function StatusChips({ view }: { view: SheetView }) {
  const status =
    view.status === "signed_off"
      ? t("statusSignedOff")
      : view.status === "checked"
        ? fill(t("statusChecked"), { code: view.code ?? "" })
        : t("statusDraft");
  const chip = "rounded-full border px-2 text-xs leading-5";
  return (
    <>
      <span className={`${chip} ${view.code === "C" ? "border-copper text-copper" : "border-slate text-ink"}`}>{status}</span>
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

  // Frozen columns first: react-data-grid moves them to the start edge, so screen order matches indexes.
  const columns = useMemo(
    () => [...view.columns.filter((c) => c.frozen), ...view.columns.filter((c) => !c.frozen)],
    [view.columns],
  );
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
  const marks = useMemo(() => commentMarks(comments, columns), [comments, columns]);

  // Row heights in the real font once it has loaded; a row with a Suggested change holds two lines.
  const measure = useMemo(makeMeasure, []);
  const [fontsLoaded, setFontsLoaded] = useState(0);
  useEffect(() => {
    let live = true;
    void document.fonts?.ready.then(() => live && setFontsLoaded((n) => n + 1));
    return () => {
      live = false;
    };
  }, []);
  const heights = useMemo(() => {
    void fontsLoaded;
    const changed = new Set([...pending.keys()].map((k) => k.split("\u0000")[0]));
    return new Map(
      rows.map((r) => [r.id, Math.max(rowHeight(r, columns, measure), changed.has(r.id) ? linesHeight(2) : 0)]),
    );
  }, [rows, columns, measure, pending, fontsLoaded]);

  const [selection, setSelection] = useState<Range | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [popover, setPopover] = useState<{
    cell: NumberCell;
    style: CSSProperties;
    from: HTMLElement;
    focus: boolean;
  } | null>(null);
  function select(range: Range | null) {
    setSelection(range);
    setPopover(null); // a source belongs to the cell it was opened on
  }

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

  function openSource(cell: NumberCell, el: HTMLElement, focus: boolean) {
    const box = boxOf(el);
    const width = root.current?.offsetWidth ?? 0;
    if (!box) return;
    // Placed under the cell, lined up with its start edge (the right edge in RTL).
    const side = direction === "rtl" ? { right: Math.max(width - box.right, 0) } : { left: box.left };
    setPopover({ cell, style: { top: box.bottom, ...side }, from: el, focus });
  }

  function closeSource() {
    popover?.from.focus();
    setPopover(null);
  }

  const renderCell = useCallback(
    (row: ViewRow, column: SheetColumn) => {
      const vc = byKey.get(column.key)!;
      return (
        <SheetCell
          row={row}
          column={vc}
          titleColumn={titleColumn}
          direction={direction}
          pending={pending.get(cellKey(row.id, column.key))}
          marks={marks.get(cellKey(row.id, column.key))}
          collapsed={collapsed.has(row.id)}
          onToggle={toggle}
          onAccept={(id) => void decide(id, true)}
          onReject={(id) => void decide(id, false)}
        />
      );
    },
    // toggle and decide read the latest state when called
    [byKey, titleColumn, direction, pending, marks, collapsed],
  );
  const canEdit = useCallback(
    (row: ViewRow, column: SheetColumn) => why(row, byKey.get(column.key)!, titleColumn) === null,
    [byKey, titleColumn],
  );
  const editText = useCallback(
    (row: ViewRow, column: SheetColumn) => cellText(row, byKey.get(column.key)!, titleColumn),
    [byKey, titleColumn],
  );
  const total = view.total;
  const totalColumn = columns.find((c) => c.kind === "calc")?.key;
  const summary = useCallback(
    (column: SheetColumn) => {
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
          className="w-full text-end font-bold hover:text-copper"
          onClick={(event) => openSource(total, event.currentTarget, event.detail === 0)}
        >
          <Value cell={total} />
        </button>
      );
    },
    // openSource reads the layout when called
    [titleColumn, totalColumn, total, view.language],
  );

  const full = props.mode === "full";
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
      <header className="flex flex-wrap items-center gap-2 border-b border-stone px-3 py-2">
        <h2 dir="auto" className="font-semibold">
          {view.title}
        </h2>
        <StatusChips view={view} />
        <span className="text-slate">{fill(t("reviewVersion"), { n: view.version })}</span>
        {view.revision && <span className="text-slate">{fill(t("reviewRev"), { n: view.revision.no })}</span>}
        {view.pending > 0 && <span>{fill(t("sheetPending"), { n: view.pending })}</span>}
        {props.onToggleFullScreen && (
          <button
            type="button"
            aria-pressed={full}
            className="ms-auto rounded border border-slate px-2 hover:bg-stone"
            onClick={props.onToggleFullScreen}
          >
            {full ? t("sheetLeaveFullScreen") : t("sheetFullScreen")}
          </button>
        )}
      </header>
      {view.sample && (
        <p role="note" className="bg-stone px-3 py-1 text-ink">
          {t("sheetSample")}
        </p>
      )}
      {notice && (
        <p role="alert" className="flex items-start justify-between gap-2 px-3 py-1 text-copper">
          <span>{notice}</span>
          <button type="button" className="rounded px-2 text-ink hover:bg-stone" onClick={() => setNotice(null)}>
            {t("close")}
          </button>
        </p>
      )}
      <div lang={view.language} className="min-h-0 flex-1">
        <Grid<ViewRow>
          ref={grid}
          label={view.title}
          columns={gridColumns}
          rows={rows}
          direction={direction}
          rowHeight={(row) => heights.get(row.id) ?? linesHeight(1)}
          renderCell={renderCell}
          canEdit={canEdit}
          editText={editText}
          onCommit={(row, column, text) => {
            const r = rows.indexOf(row);
            const c = columns.findIndex((x) => x.key === column.key);
            if (r >= 0 && c >= 0) sendBlock({ row: r, col: c }, [[text]]);
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
          onPaste={(at, text) => sendBlock(at, parseTsv(text))}
          onActivate={(row, column, el, byKey) => {
            const cell = row.cells[column.key];
            if (isNumber(cell) && !pending.has(cellKey(row.id, column.key))) openSource(cell, el, byKey);
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
          onClose={closeSource}
        />
      )}
    </div>
  );
}
