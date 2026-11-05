// A table card (kind "rows"): prices to keep (prices_propose), the columns of a BOQ import (boq_import). With `tick`, the
// engineer ticks the rows to take, and Keep sends them as rows_ok; Refuse sends none. Once sent, or settled in the
// stream, the rows left out are struck through (never by colour alone) and a line says how many were kept.
import { useState } from "react";
import { fill, pick, t } from "../../i18n";
import type { CardKindProps } from "./cardKinds";

const REFUSE = "no"; // takes nothing: no rows (core/qsone/engine/types.py)

export function RowsCard({ card, onAnswer, sending, label }: CardKindProps) {
  const [ticked, setTicked] = useState<number[]>([]);
  const payload = card.payload ?? {};
  const columns = payload.columns ?? [];
  const rows = payload.rows ?? [];
  const tickable = Boolean(payload.tick && rows.length);
  const settled = card.status === "settled";
  const open = !settled && card.status !== "withdrawn";
  const shownTicked = settled && card.rows_ok ? card.rows_ok : card.choice === REFUSE ? [] : ticked;

  const tick = (i: number) => setTicked((all) => (all.includes(i) ? all.filter((r) => r !== i) : [...all, i]));
  function send(option: string) {
    if (option === REFUSE || !tickable) return onAnswer(option);
    onAnswer(option, { rows_ok: [...ticked].sort((a, b) => a - b) });
  }

  return (
    <>
      {rows.length > 0 && (
        <table className="text-start">
          <thead>
            <tr>
              {open && tickable && <th />}
              {columns.map((c) => (
                <th key={c.key} scope="col" className="px-2 text-start font-semibold">
                  {pick(c.label)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className={!open && payload.tick && !shownTicked.includes(i) ? "text-slate line-through" : undefined}
              >
                {open && tickable && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={fill(t("tickRow"), { n: i + 1 })}
                      checked={ticked.includes(i)}
                      disabled={sending}
                      onChange={() => tick(i)}
                    />
                  </td>
                )}
                {columns.map((c) => (
                  <td key={c.key} dir="auto" className="px-2">
                    {row[c.key] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {settled && tickable && (
        <p className="text-slate">{fill(t("rowsKept"), { n: shownTicked.length, total: rows.length })}</p>
      )}
      {open && (
        <div className="flex flex-wrap gap-2">
          {card.options.map((option) => (
            <button
              key={option}
              type="button"
              disabled={sending || (option !== REFUSE && tickable && ticked.length === 0)}
              onClick={() => send(option)}
              className={`rounded-md px-3 py-1 disabled:opacity-40 ${option === REFUSE ? "border border-ink" : "bg-ink text-paper"}`}
            >
              {label(option)}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
