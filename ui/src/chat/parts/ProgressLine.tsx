// The Progress Line: one line per agent at work, its name and what it is doing now. Each line is updated in place.
// It is in the Brief's language (the engineer's, for that Brief), not the page's: an Arabic Brief in the English
// page shows Arabic progress, as its reply is.
import { dir, type Language, pick, t, useLanguage } from "../../i18n";
import type { ProgressData } from "./types";

export function ProgressLine({ items, lang }: { items: { id: string; data: ProgressData }[]; lang?: Language }) {
  useLanguage();
  if (items.length === 0) return null;
  return (
    <ul aria-label={t("progressLine")} aria-live="polite" className="flex flex-col gap-0.5 text-slate">
      {items.map(({ id, data }) => {
        const said = data.lang ?? lang;
        return (
          <li key={id} lang={said} dir={said ? dir(said) : undefined}>
            <span className="font-semibold text-ink">{pick(data.agent, said)}</span>{" "}
            <span dir="auto">{pick(data.text, said)}</span>
          </li>
        );
      })}
    </ul>
  );
}
