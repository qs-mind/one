// A table card (kind "rows"): prices to keep (prices_propose), the columns of a BOQ import (boq_import). With `tick`, the
// engineer ticks the rows to take, and Keep sends them as rows_ok; Refuse sends none. Once sent, or settled in the
// stream, the rows left out are struck through (never by colour alone); the card's folded line says how many were kept.
// The card is narrow (the chat): the table keeps its columns readable and scrolls sideways inside the card; each cell
// finds its own direction, and a long value shows two lines with the whole of it as the cell's title.
import { useState } from "react";
import { BidiText } from "../bidi";
import { fill, pick, t } from "../../i18n";
import type { CardKindProps } from "./cardKinds";

const REFUSE = "no"; // takes nothing: no rows (core/qsone/engine/types.py)

function Cell({ value }: { value: string }) {
  return (
    <td dir="auto" title={value || undefined} className="min-w-[5rem] max-w-[14rem] px-2 py-1 align-top">
      <span className="line-clamp-2 break-words">
        <BidiText text={value} />
      </span>
    </td>
  );
}

export function RowsCard({ card, onAnswer, sending, label, lang }: CardKindProps) {
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
        <div data-rows-scroll className="-mx-1 max-w-full overflow-x-auto px-1">
          <table className="w-max min-w-full border-collapse text-start">
            <thead>
              <tr>
                {open && tickable && <th />}
                {columns.map((c) => (
                  <th
                    key={c.key}
                    scope="col"
                    dir="auto"
                    className="min-w-[5rem] max-w-[14rem] px-2 py-1 text-start align-bottom font-semibold"
                  >
                    {pick(c.label, lang)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={i}
                  className={`border-t border-stone ${!open && payload.tick && !shownTicked.includes(i) ? "text-slate line-through" : ""}`}
                >
                  {open && tickable && (
                    <td className="px-1 py-1 align-top">
                      <input
                        type="checkbox"
                        aria-label={fill(t("tickRow", lang), { n: i + 1 })}
                        checked={ticked.includes(i)}
                        disabled={sending}
                        onChange={() => tick(i)}
                      />
                    </td>
                  )}
                  {columns.map((c) => (
                    <Cell key={c.key} value={row[c.key] ?? ""} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
