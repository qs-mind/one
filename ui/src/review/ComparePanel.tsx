// Two moments of one Deliverable side by side, as the core compared them: in a sheet, each changed cell from → to,
// added rows in Ink, removed rows struck; in a document, the words struck and inserted. Nothing is diffed here.
import { useEffect, useState } from "react";
import { deliverablesApi } from "../deliverables/api";
import type { Compare, View } from "../deliverables/types";
import { dir, pick, t, type Text } from "../i18n";
import { cellPlace, cellValue, columnName, rowName } from "./place";

export type ComparePanelProps = {
  projectId: string;
  deliverableId: string;
  /** "v:<n>" (a Saved version) or "r:<n>" (a Revision). */
  from: string;
  to: string;
};

const at = (key: string) => {
  const [kind, n] = key.split(":");
  return kind === "r" ? { revision: Number(n) } : { version: Number(n) };
};

export function ComparePanel({ projectId, deliverableId, from, to }: ComparePanelProps) {
  const [found, setFound] = useState<{ diff: Compare; a: View; b: View } | null>(null);
  const [failed, setFailed] = useState<Text | null>(null);

  useEffect(() => {
    let live = true;
    setFound(null);
    setFailed(null);
    void Promise.all([
      deliverablesApi.compare(projectId, deliverableId, from, to),
      deliverablesApi.view(projectId, deliverableId, at(from)),
      deliverablesApi.view(projectId, deliverableId, at(to)),
    ]).then(([diff, a, b]) => {
      if (!live) return;
      if (diff.ok && a.ok && b.ok) setFound({ diff: diff.data, a: a.data, b: b.data });
      else setFailed(!diff.ok ? diff.error : !a.ok ? a.error : !b.ok ? b.error : null);
    });
    return () => {
      live = false;
    };
  }, [projectId, deliverableId, from, to]);

  if (failed)
    return (
      <p role="alert" className="text-copper">
        {pick(failed)}
      </p>
    );
  if (!found) return <p className="text-slate">{t("deliverableLoading")}</p>;
  const { diff, a, b } = found;
  // from old to new in the reading direction: ← in Arabic, → in English
  const arrow = dir(b.language) === "rtl" ? "←" : "→";
  // A row's name comes from the side it is on: a removed row is only in the older view.
  const name = (id: string) => (b.kind === "sheet" && b.rows.some((r) => r.id === id) ? rowName(b, id) : rowName(a, id));

  if ("rows" in diff) {
    const changed = diff.rows.filter((r) => r.change !== "same");
    const total = diff.total;
    const totalMoved = cellValue(total.from) !== cellValue(total.to);
    if (changed.length === 0 && !totalMoved) return <p className="text-slate">{t("reviewNoDifference")}</p>;
    return (
      <div dir={dir(b.language)} lang={b.language} className="flex flex-col gap-1">
        <ul className="flex flex-col gap-1">
          {changed.map((row) => {
            const label =
              row.change === "added" ? t("reviewAdded") : row.change === "removed" ? t("reviewRemoved") : row.change === "moved" ? t("reviewMovedRow") : null;
            const title = <bdi dir="auto">{name(row.id)}</bdi>;
            return (
              <li key={row.id} className={`rounded border border-stone p-1 ${row.change === "added" ? "font-semibold text-ink" : ""}`}>
                <span className="flex flex-wrap items-baseline gap-2">
                  {row.change === "removed" ? <del className="text-slate">{title}</del> : title}
                  {label && <span className="text-xs text-slate">{label}</span>}
                </span>
                {row.change !== "removed" && Object.keys(row.cells).length > 0 && (
                  <ul className="ps-3 font-normal">
                    {Object.entries(row.cells).map(([key, cell]) => (
                      <li key={key} className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-slate">{columnName(b, key) || columnName(a, key) || t("deliverableTitle")}</span>
                        <del className="text-slate">
                          <bdi dir="auto">{cellValue(cell.from)}</bdi>
                        </del>
                        <span aria-hidden className="text-slate">
                          {arrow}
                        </span>
                        <ins className="text-ink no-underline">
                          <bdi dir="auto">{cellValue(cell.to)}</bdi>
                        </ins>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
        {totalMoved && (
          <p className="flex flex-wrap items-baseline gap-x-2 font-semibold">
            <span>{cellPlace(b, "total")}</span>
            <del className="font-normal text-slate">
              <bdi dir="auto">{cellValue(total.from)}</bdi>
            </del>
            <span aria-hidden className="text-slate">
              {arrow}
            </span>
            <bdi dir="auto">{cellValue(total.to)}</bdi>
          </p>
        )}
      </div>
    );
  }

  const changed = diff.blocks.filter((x) => x.change !== "same");
  if (changed.length === 0) return <p className="text-slate">{t("reviewNoDifference")}</p>;
  return (
    <ol dir={dir(b.language)} lang={b.language} className="flex flex-col gap-2">
      {changed.map((block) => (
        <li key={block.id} className="rounded border border-stone p-1">
          {block.change !== "changed" && (
            <span className="text-xs text-slate">
              {block.change === "added" ? t("reviewAdded") : block.change === "removed" ? t("reviewRemoved") : t("reviewMovedRow")}
            </span>
          )}
          <p dir="auto" className="whitespace-pre-wrap">
            {block.segments.map((s, i) =>
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
        </li>
      ))}
    </ol>
  );
}
