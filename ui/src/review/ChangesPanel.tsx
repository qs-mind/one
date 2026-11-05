// The Suggested changes of one Deliverable: "Update from Project Records" first, then each pending change with who
// made it, why, its old value struck and its new one beside it, what the QS Calc Engine would recalculate with it,
// and ✓ ✗. The engineer decides; nothing here computes. Changes that no longer apply are listed in plain words.
import { useState } from "react";
import { deliverablesApi } from "../deliverables/api";
import type { Anchor } from "../canvas/types";
import type { CellChange, Change, RecordsCell, Segment, View } from "../deliverables/types";
import { asCell } from "../deliverables/types";
import { fill, pick, t, type Text } from "../i18n";
import { fieldKey, numberName } from "../viewers/sheet/clipboard";
import { titleColumnOf } from "../viewers/sheet/heights";
import { authorName, cellPlace, cellValue, rowName, when } from "./place";

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
};

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

function OldNew({ before, after }: { before: string | null; after: string | null }) {
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2">
      {before !== null && (
        <del className="text-slate">
          <bdi dir="auto">{before}</bdi>
        </del>
      )}
      <span aria-hidden className="text-slate">
        →
      </span>
      <ins className="font-semibold text-ink no-underline">
        <bdi dir="auto">{after ?? "—"}</bdi>
      </ins>
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

export function ChangesPanel({ projectId, view, changes, stale, onChanged, onLocate, announce }: ChangesPanelProps) {
  const [failed, setFailed] = useState<Text | null>(null);
  const [updateFirst, setUpdateFirst] = useState<string[] | null>(null); // ids refused until the update joins them
  const [busy, setBusy] = useState(false);
  const pending = changes
    .filter((c) => c.status === "pending")
    .sort((a, b) => Number(b.op.op === "update_from_records") - Number(a.op.op === "update_from_records"));
  const update = pending.find((c) => c.op.op === "update_from_records");
  const mine = pending.filter((c) => c.author === "engineer");

  async function accept(which: { ids: string[] } | { mine: true }) {
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
    onChanged();
  }

  async function reject(ids: string[]) {
    setBusy(true);
    setFailed(null);
    setUpdateFirst(null);
    const answer = await deliverablesApi.reject(projectId, view.id, ids);
    setBusy(false);
    if (!answer.ok) return setFailed(answer.error);
    announce?.(t("reviewRejected"));
    onChanged();
  }

  const button = "rounded border border-slate px-2 py-0.5 hover:bg-stone disabled:opacity-40";
  return (
    <section aria-label={t("reviewChanges")} className="flex flex-col gap-3">
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
              className="rounded border border-ink px-2 py-0.5 text-ink hover:bg-stone"
              onClick={() => void accept({ ids: [update.id, ...updateFirst.filter((id) => id !== update.id)] })}
            >
              {t("reviewAcceptWithUpdate")}
            </button>
          )}
        </div>
      )}
      {pending.length === 0 && <p className="text-slate">{t("reviewNoChanges")}</p>}
      <ol className="flex flex-col gap-2">
        {pending.map((change) => {
          const records = change.op.op === "update_from_records";
          return (
            <li key={change.id} className={`flex flex-col gap-1 rounded-md border p-2 ${records ? "border-ink" : "border-stone"}`}>
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
                    className="rounded border border-slate px-2 hover:bg-stone disabled:opacity-40"
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
                    className="rounded border border-slate px-2 text-copper hover:bg-stone disabled:opacity-40"
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
