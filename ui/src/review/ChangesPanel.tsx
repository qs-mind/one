// The Suggested changes of one Deliverable, the BOQ change review: "Update from Project Records" first, then each
// pending change with who made it, why, the source of its new number, its new value in Copper over the old one struck
// in Slate, what the QS Calc Engine would recalculate with it, and ✓ ✗. The engineer decides; nothing here computes.
// Accepting applies at once, and the owner shows «اتقبل · تراجع» (`onAccepted`). J/K or ↑/↓ move between changes
// (by the key's place, so the Arabic layout works too), A accepts and R rejects; the change moved to reveals its new
// value (220 ms, ONE's ease; at once with reduced motion) and the viewer scrolls to it. Changes that no longer apply
// are listed in plain words.
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { deliverablesApi, type Accepted, type Rejected } from "../deliverables/api";
import type { Anchor } from "../project/types";
import type { CellChange, Change, RecordsCell, Segment, View } from "../deliverables/types";
import { asCell, isNumber } from "../deliverables/types";
import { fill, pick, t, type Text } from "../i18n";
import { useSourceCard } from "../sources/useSourceCard";
import { DUR, play } from "../ui/motion";
import { REVEAL } from "../viewers/sheet/cells";
import { fieldKey, numberName } from "../viewers/sheet/clipboard";
import { titleColumnOf } from "../viewers/sheet/heights";
import { authorName, cellPlace, cellValue, columnName, rowName, when } from "./place";

const FOLD = 5; // more recalculated cells than this are folded

export type ChangesPanelProps = {
  projectId: string;
  view: View;
  changes: Change[];
  stale: Change[];
  /** After an accept or a reject: the owner loads the Deliverable again. */
  onChanged: () => void;
  /** Scrolls the viewer to a change's cell or block. */
  onLocate?: (anchor: Anchor) => void;
  /** Says a finished accept or reject in the viewer's one status region. */
  announce?: (line: string) => void;
  /** After an accept: its answer (with its Undo), and whether it came from the keyboard (the focus stays here). */
  onAccepted?: (answer: Accepted, how: { keys: boolean }) => void;
  /** After a reject, with its Undo («اترفض · تراجع»). */
  onRejected?: (answer: Rejected, how: { keys: boolean }) => void;
  /** The change the engineer is on, for the viewer to show it; null when none waits. */
  onCurrent?: (change: Change | null) => void;
};

/** Keys by their place on the keyboard, not the letter they type: J is «ت» on an Arabic layout. */
const MOVES: Record<string, 1 | -1> = { KeyJ: 1, ArrowDown: 1, KeyK: -1, ArrowUp: -1 };

/** The column a sheet op edits, so the change can name its cell. */
function columnOf(view: View, change: Change): string | undefined {
  if (view.kind !== "sheet") return undefined;
  const op = change.op;
  if (op.op === "set_number") return view.columns.find((c) => c.kind === "number" && numberName(c) === op.name)?.key;
  if (op.op === "set_field") return view.columns.find((c) => c.kind === "text" && fieldKey(c) === op.key)?.key;
  if (op.op === "set_section_title") return titleColumnOf(view.columns);
  return undefined;
}

/** The row or block a change is about (a part id, only used to scroll; never shown). */
function targetOf(change: Change): string | null {
  const op = change.op as { row?: string; block?: string };
  return op.row ?? op.block ?? null;
}

/** The new value in Copper, then the old one struck through in Slate. */
function OldNew({ before, after }: { before: string | null; after: string | null }) {
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2">
      <ins data-reveal className="inline-block font-semibold text-copper no-underline">
        <bdi dir="auto">{after ?? "—"}</bdi>
      </ins>
      {before !== null && (
        <del className="text-slate">
          <bdi dir="auto">{before}</bdi>
        </del>
      )}
    </span>
  );
}

function Segments({ segments }: { segments: Segment[] }) {
  return (
    <p dir="auto" className="whitespace-pre-wrap">
      {segments.map((s, i) =>
        s.op === "del" ? (
          <del key={i} className="text-slate">
            {s.text}
          </del>
        ) : s.op === "ins" ? (
          <ins key={i} className="font-semibold text-ink no-underline">
            {s.text}
          </ins>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </p>
  );
}

function why(cell: RecordsCell): string {
  if ("recalculated" in cell.why) return t("sheetRecalculated");
  return cell.why.corrected ? fill(t("reviewCorrected"), { reason: cell.why.corrected }) : t("reviewFieldChanged");
}

/** A list of cells old → new (recalculated cells, or the cells an Update from Project Records brings). */
function Cells({ view, cells, onLocate }: { view: View; cells: (CellChange | RecordsCell)[]; onLocate?: (a: Anchor) => void }) {
  const line = (cell: CellChange | RecordsCell, i: number) => (
    <li key={i} className="flex flex-wrap items-baseline gap-x-2">
      <button
        type="button"
        className="text-start underline decoration-slate/40 hover:text-copper"
        onClick={() => cell.row && onLocate?.({ row: cell.row, column: cell.column })}
      >
        <bdi dir="auto">{cellPlace(view, cell.row, view.kind === "sheet" ? cell.column : undefined)}</bdi>
      </button>
      <OldNew before={cellValue(cell.before)} after={cell.after ? cellValue(cell.after) : null} />
      {"why" in cell && <span className="text-slate">{why(cell)}</span>}
    </li>
  );
  const shown = cells.slice(0, FOLD);
  const folded = cells.slice(FOLD);
  return (
    <>
      <ul className="flex flex-col gap-0.5">{shown.map(line)}</ul>
      {folded.length > 0 && (
        <details>
          <summary className="cursor-pointer text-slate">{fill(t("reviewMore"), { n: folded.length })}</summary>
          <ul className="flex flex-col gap-0.5">{folded.map((c, i) => line(c, i + FOLD))}</ul>
        </details>
      )}
    </>
  );
}

/** What the change does, in words and old → new. */
function What({ view, change, onLocate }: { view: View; change: Change; onLocate?: (a: Anchor) => void }) {
  const op = change.op;
  const target = targetOf(change);
  const locate = () => target && onLocate?.({ row: target, column: columnOf(view, change) });
  const place = (label: string) => (
    <button type="button" className="text-start underline decoration-slate/40 hover:text-copper" onClick={locate}>
      <bdi dir="auto">{label}</bdi>
    </button>
  );
  switch (op.op) {
    case "update_from_records":
      return <Cells view={view} cells={op.cells} onLocate={onLocate} />;
    case "set_number":
    case "set_field":
    case "set_section_title": {
      const before = asCell(change.before);
      return (
        <p className="flex flex-wrap items-baseline gap-x-2">
          {place(cellPlace(view, op.row, columnOf(view, change)))}
          <OldNew before={before ? cellValue(before) : null} after={cellValue(asCell(change.after))} />
        </p>
      );
    }
    case "add_item_row":
      return <p>{place(fill(t("reviewOpAddRow"), { code: op.code }))}</p>;
    case "add_section":
      return <p>{place(fill(t("reviewOpAddSection"), { title: op.title }))}</p>;
    case "remove_row":
      return (
        <p className="flex gap-2">
          <span>{t("reviewOpRemoveRow")}</span>
          <del className="text-slate">{place(cellPlace(view, op.row))}</del>
        </p>
      );
    case "move_row":
      return (
        <p className="flex gap-2">
          <span>{t("reviewOpMoveRow")}</span>
          {place(cellPlace(view, op.row))}
        </p>
      );
    case "set_columns":
      return <p>{t("reviewOpColumns")}</p>;
    default: {
      const label =
        op.op === "insert_block"
          ? t("reviewOpInsertBlock")
          : op.op === "remove_block"
            ? t("reviewOpRemoveBlock")
            : op.op === "move_block"
              ? t("reviewOpMoveBlock")
              : rowName(view, target);
      return (
        <div className="flex flex-col gap-1">
          {place(label)}
          {change.segments && op.op !== "move_block" && <Segments segments={change.segments} />}
        </div>
      );
    }
  }
}

/** Where the change's new number comes from: its source, which opens its card; or that the engineer typed it. */
function SourceOf({ view, change, open }: { view: View; change: Change; open: (from: HTMLElement, label: string, focus: boolean) => void }) {
  const after = asCell(change.after);
  if (!isNumber(after)) return null;
  const source = after.source ? change.sources?.[after.source] : undefined;
  if (!source) return change.author === "engineer" ? <span className="text-sm text-slate">{t("changeTyped")}</span> : null;
  const label = fill(t("changeSource"), { title: source.title });
  const column = columnOf(view, change);
  return (
    <button
      type="button"
      aria-label={label}
      className="self-start rounded-md bg-stone px-2 py-0.5 text-sm hover:text-copper focus-visible:outline-2 focus-visible:outline-ink"
      onClick={(event) => open(event.currentTarget, column ? columnName(view, column) : "", event.detail === 0)}
    >
      <bdi dir="auto">{label}</bdi>
      {(after.dated ?? source.dated) && <span className="text-slate"> · {after.dated ?? source.dated}</span>}
    </button>
  );
}

export function ChangesPanel({ projectId, view, changes, stale, onChanged, onLocate, announce, onAccepted, onRejected, onCurrent }: ChangesPanelProps) {
  const [failed, setFailed] = useState<Text | null>(null);
  const [updateFirst, setUpdateFirst] = useState<string[] | null>(null); // ids refused until the update joins them
  const [busy, setBusy] = useState(false);
  const pending = changes
    .filter((c) => c.status === "pending")
    .sort((a, b) => Number(b.op.op === "update_from_records") - Number(a.op.op === "update_from_records"));
  const update = pending.find((c) => c.op.op === "update_from_records");
  const mine = pending.filter((c) => c.author === "engineer");
  const sourceCard = useSourceCard(projectId);

  // The change the engineer is on: kept by its place in the list, so after an accept the next one takes it
  const [at, setAt] = useState(0);
  const index = Math.min(at, Math.max(pending.length - 1, 0));
  const currentChange = pending[index] ?? null;
  const items = useRef(new Map<string, HTMLLIElement>());
  const moved = useRef(false);
  const reported = useRef(onCurrent);
  reported.current = onCurrent;
  useEffect(() => reported.current?.(currentChange), [currentChange?.id]); // only when the change moves
  useLayoutEffect(() => {
    if (!moved.current || !currentChange) return;
    moved.current = false;
    const item = items.current.get(currentChange.id);
    for (const el of item?.querySelectorAll("[data-reveal]") ?? []) void play(el, REVEAL, DUR.base);
  }, [currentChange?.id]); // only when the change moves

  function moveTo(next: number) {
    const change = pending[next];
    if (!change) return;
    moved.current = next !== index;
    setAt(next);
    items.current.get(change.id)?.focus();
    const target = targetOf(change);
    if (target) onLocate?.({ row: target, column: columnOf(view, change) });
  }

  function onKeys(event: KeyboardEvent<HTMLOListElement>) {
    const target = event.target as HTMLElement;
    if (event.ctrlKey || event.metaKey || event.altKey || target.matches("input, textarea, select")) return;
    const step = MOVES[event.code];
    if (step) {
      event.preventDefault();
      return moveTo(Math.min(Math.max(index + step, 0), pending.length - 1));
    }
    if (!currentChange || busy) return;
    if (event.code === "KeyA") {
      event.preventDefault();
      void accept({ ids: [currentChange.id] }, true);
    } else if (event.code === "KeyR") {
      event.preventDefault();
      void reject([currentChange.id], true);
    }
  }

  async function accept(which: { ids: string[] } | { mine: true }, keys = false) {
    setBusy(true);
    setFailed(null);
    setUpdateFirst(null);
    const answer = await deliverablesApi.accept(projectId, view.id, which);
    setBusy(false);
    if (!answer.ok) {
      setFailed(answer.error);
      // UPDATE_FIRST: Project Records moved, so the update must be accepted with them
      if (answer.status === 409 && answer.field === "ids" && update)
        setUpdateFirst("ids" in which ? which.ids : mine.map((c) => c.id));
      return;
    }
    const { version } = answer.data;
    announce?.(version === null ? t("reviewNothingAccepted") : fill(t("reviewAccepted"), { n: version }));
    if (version !== null) onAccepted?.(answer.data, { keys });
    onChanged();
  }

  async function reject(ids: string[], keys = false) {
    setBusy(true);
    setFailed(null);
    setUpdateFirst(null);
    const answer = await deliverablesApi.reject(projectId, view.id, ids);
    setBusy(false);
    if (!answer.ok) return setFailed(answer.error);
    announce?.(t("reviewRejected"));
    onRejected?.(answer.data, { keys });
    onChanged();
  }

  const button = "rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone disabled:opacity-40";
  return (
    <section ref={sourceCard.host} aria-label={t("reviewChanges")} className="relative flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <button type="button" className={button} disabled={busy || pending.length === 0} onClick={() => void accept({ ids: pending.map((c) => c.id) })}>
          {t("reviewAcceptAll")}
        </button>
        <button type="button" className={button} disabled={busy || mine.length === 0} onClick={() => void accept({ mine: true })}>
          {t("reviewAcceptMine")}
        </button>
        <button type="button" className={button} disabled={busy || pending.length === 0} onClick={() => void reject(pending.map((c) => c.id))}>
          {t("reviewRejectAll")}
        </button>
      </div>
      {failed && (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-copper">
          <span>{pick(failed)}</span>
          {updateFirst && update && (
            <button
              type="button"
              className="rounded-lg border border-ink px-3 py-1 text-ink hover:bg-stone"
              onClick={() => void accept({ ids: [update.id, ...updateFirst.filter((id) => id !== update.id)] })}
            >
              {t("reviewAcceptWithUpdate")}
            </button>
          )}
        </div>
      )}
      {pending.length === 0 ? (
        <p className="text-slate">{t("reviewNoChanges")}</p>
      ) : (
        <p className="text-xs text-slate">{t("reviewKeys")}</p>
      )}
      <ol aria-label={t("reviewChanges")} className="flex flex-col gap-3" onKeyDown={onKeys}>
        {pending.map((change, i) => {
          const records = change.op.op === "update_from_records";
          const current = i === index;
          return (
            <li
              key={change.id}
              ref={(el) => {
                if (el) items.current.set(change.id, el);
                else items.current.delete(change.id);
              }}
              data-change
              aria-current={current || undefined}
              tabIndex={current ? 0 : -1}
              onFocus={(event) => {
                if (event.target === event.currentTarget && i !== index) setAt(i);
              }}
              className={`flex flex-col gap-2 rounded-xl border bg-paper px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-ink/30 ${
                records || current ? "border-ink" : "border-stone"
              }`}
            >
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-semibold">{records ? t("reviewRecordsMoved") : authorName(change.author)}</span>
                {records && <span className="text-slate">{authorName(change.author)}</span>}
                <span className="text-xs text-slate">{when(change.created_at)}</span>
                <span className="ms-auto flex gap-1">
                  <button
                    type="button"
                    aria-label={t("sheetAccept")}
                    title={t("sheetAccept")}
                    disabled={busy}
                    className="rounded-md border border-ink/20 px-2.5 py-0.5 hover:bg-stone disabled:opacity-40"
                    onClick={() => void accept({ ids: [change.id] })}
                  >
                    <span aria-hidden>✓ </span>
                    {t("sheetAccept")}
                  </button>
                  <button
                    type="button"
                    aria-label={t("sheetReject")}
                    title={t("sheetReject")}
                    disabled={busy}
                    className="rounded-md border border-ink/20 px-2.5 py-0.5 text-copper hover:bg-stone disabled:opacity-40"
                    onClick={() => void reject([change.id])}
                  >
                    <span aria-hidden>✗ </span>
                    {t("sheetReject")}
                  </button>
                </span>
              </div>
              {change.reason && (
                <p dir="auto" className="text-slate">
                  {change.reason}
                </p>
              )}
              {change.note && <p className="text-copper">{pick(change.note)}</p>}
              <SourceOf
                view={view}
                change={change}
                open={(from, label, focus) => {
                  const after = asCell(change.after);
                  if (isNumber(after)) sourceCard.open(from, after, change.sources ?? {}, { label, focus });
                }}
              />
              <What view={view} change={change} onLocate={onLocate} />
              {change.follows.length > 0 && (
                <div className="flex flex-col gap-0.5 ps-3 text-sm">
                  <span className="text-slate">{t("reviewFollows")}</span>
                  <Cells view={view} cells={change.follows} onLocate={onLocate} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {sourceCard.card}
      {stale.length > 0 && (
        <details>
          <summary className="cursor-pointer text-slate">
            {t("reviewStale")} ({stale.length})
          </summary>
          <p className="text-slate">{t("reviewStaleWhy")}</p>
          <ol className="mt-1 flex flex-col gap-1">
            {[...stale].reverse().map((change) => (
              <li key={change.id} className="rounded-md border border-stone p-2 text-slate">
                <span className="me-2">{authorName(change.author)}</span>
                <What view={view} change={change} onLocate={onLocate} />
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
