// A table card (kind "rows", 3.2): prices to keep, or the columns of a BOQ import. With `tick` the engineer ticks the
// rows to take and the first option sends them as rows_ok; "no" sends none. With `meanings` each row is a column of
// the sheet, its meaning picked from the core's list (set as mapped), and the first option sends every column's
// meaning by letter; the choices stay folded behind "Check the columns" (Kareem, 8 Nov: two dozen «Not used» choices
// in the thread meant nothing). Once answered, the rows left out are struck through, never by colour alone. A row's
// number with a source opens that source in ONE's viewer. A wide table scrolls sideways inside the card.
import { useState } from "react";
import { Num } from "@/design/Num";
import { Button } from "@/design/ui/button";
import { Checkbox } from "@/design/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import { cards } from "@/texts/cards";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import { ConfirmationAction, ConfirmationActions } from "../ai/confirmation";
import type { CardAnswer, CardData, Source } from "../parts";

const REFUSE = "no"; // takes nothing (core/qsone/engine/types.py)

type RowsBodyProps = {
  card: CardData;
  open: boolean;
  busy: boolean;
  label: (option: string) => string;
  onAnswer: (choice: string, extra?: CardAnswer) => void;
  onOpenSource?: (source: Source) => void;
};

export function RowsBody({ card, open, busy, label, onAnswer, onOpenSource }: RowsBodyProps) {
  const t = useText();
  const payload = card.payload ?? {};
  const columns = payload.columns ?? [];
  const rows = payload.rows ?? [];
  const sources = payload.row_sources ?? [];
  const meaningKey = payload.meanings?.length ? payload.meaning_column : undefined;
  const tickable = Boolean(payload.tick && rows.length);
  const [ticked, setTicked] = useState<number[]>([]);
  const [meanings, setMeanings] = useState<Record<string, string>>(() =>
    meaningKey ? Object.fromEntries(rows.map((r) => [r.column ?? "", r[meaningKey] ?? "none"])) : {},
  );
  const [unfolded, setUnfolded] = useState(false);
  const kept = card.status === "settled" && card.rows_ok ? card.rows_ok : card.choice === REFUSE ? [] : ticked;
  const meaningWords = (key: string) => {
    const named = payload.meanings?.find((m) => m.key === key);
    return named ? t(named.label) : key;
  };

  const send = (option: string) => {
    if (option === REFUSE) return onAnswer(option);
    if (meaningKey) return onAnswer(option, { answers: meanings });
    if (tickable) return onAnswer(option, { rows_ok: [...ticked].sort((a, b) => a - b) });
    onAnswer(option);
  };
  const words = (option: string) => (meaningKey && option !== REFUSE ? t(cards.keepColumns) : label(option));

  const taken = rows
    .map((row) => row.column ?? "")
    .filter((letter) => (meanings[letter] ?? "none") !== "none")
    .map((letter) => `${meaningWords(meanings[letter]!)}: ${letter}`);
  const folded = Boolean(meaningKey) && open && !unfolded;

  function cell(row: Record<string, string>, i: number, key: string, heading: string) {
    const value = row[key] ?? "";
    if (key === meaningKey) {
      const letter = row.column ?? "";
      const chosen = (card.status === "settled" && card.answers?.[letter]) || meanings[letter] || "none";
      if (!open) return meaningWords(chosen);
      const items = (payload.meanings ?? []).map((m) => ({ value: m.key, label: t(m.label) }));
      return (
        <Select items={items} value={chosen} disabled={busy} onValueChange={(next) => setMeanings((all) => ({ ...all, [letter]: String(next) }))}>
          <SelectTrigger className="h-11 min-w-36" aria-label={t(cards.columnMeaning, { letter })}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {items.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    const source = key === payload.number_column ? sources[i] : null;
    if (source)
      return (
        <Button variant="link" aria-label={t(cards.sourceOf, { value })} title={heading} onClick={() => onOpenSource?.(source)}>
          <Num>{value}</Num>
        </Button>
      );
    return (
      <span dir={textDir(value)} title={value || undefined} className="line-clamp-2 break-words">
        {value}
      </span>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {meaningKey && open && (
        <div className="flex flex-col items-start gap-1">
          {taken.length > 0 && (
            <p data-columns-taken dir={textDir(taken.join(" "))} className="text-muted-foreground">
              {taken.join(" · ")}
            </p>
          )}
          <Button variant="link" aria-expanded={unfolded} onClick={() => setUnfolded(!unfolded)}>
            {t(unfolded ? cards.hideColumns : cards.checkColumns)}
          </Button>
        </div>
      )}
      {rows.length > 0 && !folded && (
        <div data-rows-scroll className="max-w-full overflow-x-auto">
          <table className="w-full border-collapse text-start">
            <thead>
              <tr className="text-xs text-muted-foreground">
                {open && tickable && <th aria-hidden className="w-8" />}
                {columns.map((c) => (
                  <th key={c.key} scope="col" className="px-2 py-2 text-start align-bottom font-normal">
                    {t(c.label)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={i}
                  data-left-out={(!open && payload.tick && !kept.includes(i)) || undefined}
                  className="border-t border-line data-left-out:text-muted-foreground data-left-out:line-through"
                >
                  {open && tickable && (
                    <td className="px-2 py-2 align-top">
                      <Checkbox
                        aria-label={t(cards.tickRow, { n: i + 1 })}
                        checked={ticked.includes(i)}
                        disabled={busy}
                        onCheckedChange={() => setTicked((all) => (all.includes(i) ? all.filter((r) => r !== i) : [...all, i]))}
                      />
                    </td>
                  )}
                  {columns.map((c) => (
                    <td key={c.key} className="min-w-20 max-w-56 px-2 py-2 align-top">
                      {cell(row, i, c.key, t(c.label))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && (
        <ConfirmationActions className="mt-1">
          {card.options.map((option, at) => (
            <ConfirmationAction
              key={option}
              variant={at === 0 && option !== REFUSE ? "default" : "outline"}
              disabled={busy || (option !== REFUSE && tickable && ticked.length === 0)}
              onClick={() => send(option)}
            >
              {words(option)}
            </ConfirmationAction>
          ))}
        </ConfirmationActions>
      )}
    </div>
  );
}
