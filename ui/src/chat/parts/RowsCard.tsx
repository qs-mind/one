// A table card (kind "rows"): prices to keep (prices_propose), the columns of a BOQ import (boq_import). With `tick`, the
// engineer ticks the rows to take, and Keep sends them as rows_ok; Refuse sends none. Once sent, or settled in the
// stream, the rows left out are struck through (never by colour alone); the card's folded line says how many were kept.
// The card is as wide as the chat (280 to 560 px). Below 32rem of card each row stacks: its first column on a line of
// its own, the others under it as "label: value", so every column shows whole at any chat width; from 32rem it is a
// table (which scrolls sideways inside the card if it must). Each cell finds its own direction, and a long value shows
// two lines with the whole of it as the cell's title. Table roles are set by hand: a stacked table keeps them. A row
// whose number the core gives a source (`number_column`, `row_sources`) opens that number into its source card.
import { useState, type ReactNode } from "react";
import { baseDirection, BidiText } from "../bidi";
import type { Source } from "../../deliverables/types";
import { fill, pick, t } from "../../i18n";
import { sourceLineHandlers } from "../../sources/line";
import { sourceKeys } from "../../sources/targets";
import { useSourceCard } from "../../sources/useSourceCard";
import type { CardKindProps } from "./cardKinds";

const REFUSE = "no"; // takes nothing: no rows (core/qsone/engine/types.py)

function Cell({ value, label, main, children }: { value: string; label: string; main: boolean; children?: ReactNode }) {
  return (
    <td
      role="cell"
      // only the first column takes its own direction: another cell's "label: " and margin stay in the card's, and
      // its value finds its own inside (the span)
      dir={main && baseDirection(value) ? "auto" : undefined}
      title={value || undefined}
      data-label={main ? undefined : `${label}: `}
      className={`min-w-0 align-top @lg:table-cell @lg:min-w-[5rem] @lg:max-w-[14rem] @lg:px-3 @lg:py-2.5 @lg:before:content-none ${
        main ? "basis-full pb-1 font-semibold @lg:pb-2.5 @lg:font-normal" : "me-4 flex text-slate before:shrink-0 before:whitespace-pre before:content-[attr(data-label)] @lg:me-0 @lg:text-ink"
      }`}
    >
      <span dir={!main && baseDirection(value) ? "auto" : undefined} className="line-clamp-2 break-words">
        {children ?? <BidiText text={value} />}
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
  // A row's number with its source opens in place into its source card (no number id yet: nothing is kept until
  // the engineer ticks it, so the card shows the row's own source and fetches nothing)
  const sources = payload.row_sources ?? [];
  const source = useSourceCard("");
  function sourcedNumber(i: number, value: string, label: string) {
    const from: Source = sources[i]!;
    const keys = sourceKeys({ fileId: from.file_id, locator: from.locator });
    return (
      <button
        type="button"
        aria-label={fill(t("sourceOfNumber", lang), { value })}
        className="rounded-sm border-b border-copper px-0.5 hover:bg-stone focus-visible:outline focus-visible:outline-copper"
        onClick={(event) =>
          source.open(event.currentTarget, { value, currency: rows[i]?.currency || null, number_id: null, source: "row", dated: from.dated ?? null }, { row: from }, { label, focus: event.detail === 0 })
        }
        {...sourceLineHandlers(keys)}
      >
        <bdi dir="ltr">{value}</bdi>
      </button>
    );
  }

  const tick = (i: number) => setTicked((all) => (all.includes(i) ? all.filter((r) => r !== i) : [...all, i]));
  function send(option: string) {
    if (option === REFUSE || !tickable) return onAnswer(option);
    onAnswer(option, { rows_ok: [...ticked].sort((a, b) => a - b) });
  }

  return (
    <>
      {rows.length > 0 && (
        <div ref={source.host} className="relative">
          <div data-rows-scroll className="@container -mx-1 max-w-full overflow-x-auto px-1">
            <table role="table" className="block w-full border-collapse text-start @lg:table @lg:w-max @lg:min-w-full">
              <thead role="rowgroup" className="sr-only @lg:not-sr-only @lg:table-header-group">
                <tr role="row">
                  {open && tickable && <th />}
                  {columns.map((c) => (
                    <th
                      key={c.key}
                      role="columnheader"
                      scope="col"
                      dir="auto"
                      className="min-w-[5rem] max-w-[14rem] px-3 py-2 text-start align-bottom text-sm font-semibold text-slate"
                    >
                      {pick(c.label, lang)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody role="rowgroup" className="block @lg:table-row-group">
                {rows.map((row, i) => (
                  <tr
                    key={i}
                    role="row"
                    className={`flex flex-wrap border-t border-stone py-3 @lg:table-row @lg:py-0 ${open && tickable ? "ps-8 @lg:ps-0" : ""} ${!open && payload.tick && !shownTicked.includes(i) ? "text-slate line-through" : ""}`}
                  >
                    {open && tickable && (
                      <td role="cell" className="-ms-8 w-8 shrink-0 pt-0.5 align-top @lg:ms-0 @lg:table-cell @lg:w-auto @lg:px-2 @lg:py-2.5">
                        <input
                          type="checkbox"
                          aria-label={fill(t("tickRow", lang), { n: i + 1 })}
                          checked={ticked.includes(i)}
                          disabled={sending}
                          onChange={() => tick(i)}
                        />
                      </td>
                    )}
                    {columns.map((c, n) => (
                      <Cell key={c.key} value={row[c.key] ?? ""} label={pick(c.label, lang)} main={n === 0}>
                        {c.key === payload.number_column && sources[i] ? sourcedNumber(i, row[c.key] ?? "", pick(c.label, lang)) : undefined}
                      </Cell>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {source.card}
        </div>
      )}
      {open && (
        <div className="flex flex-wrap gap-2 pt-1">
          {card.options.map((option) => (
            <button
              key={option}
              type="button"
              disabled={sending || (option !== REFUSE && tickable && ticked.length === 0)}
              onClick={() => send(option)}
              className={`rounded-lg px-4 py-2 disabled:opacity-40 ${option === REFUSE ? "border border-ink" : "bg-ink text-paper"}`}
            >
              {label(option)}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
