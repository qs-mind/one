// The Progress Line: one line per agent at work, its name and what it is doing now. Each line is updated in place.
// It is in the Brief's language (the engineer's, for that Brief), not the page's: an Arabic Brief in the English
// page shows Arabic progress, as its reply is. While the Brief is live, each new step the core reports rises in as a
// new line (150 ms); nothing here runs on a timer, and the steps of a Brief read again stay still.
import { useLayoutEffect, useRef } from "react";
import { dir, type Language, pick, t, useLanguage } from "../../i18n";
import { DUR, play } from "../../ui/motion";
import type { ProgressData } from "./types";

/** One agent's line; keyed by its step too, so a new step is a new line that rises in. */
function Line({ data, lang, live }: { data: ProgressData; lang?: Language; live: boolean }) {
  const ref = useRef<HTMLLIElement>(null);
  useLayoutEffect(() => {
    if (live && ref.current) void play(ref.current, [{ opacity: 0, transform: "translateY(0.5em)" }, { opacity: 1, transform: "none" }], DUR.short);
  }, []); // on arrival only
  return (
    <li ref={ref} lang={lang} dir={lang ? dir(lang) : undefined}>
      <span className="font-semibold text-ink">{pick(data.agent, lang)}</span>{" "}
      <span dir="auto">{pick(data.text, lang)}</span>
    </li>
  );
}

export function ProgressLine({ items, lang, live = false }: { items: { id: string; data: ProgressData }[]; lang?: Language; live?: boolean }) {
  useLanguage();
  if (items.length === 0) return null;
  return (
    <ul aria-label={t("progressLine")} aria-live="polite" className="flex flex-col gap-1 text-slate">
      {items.map(({ id, data }) => {
        const said = data.lang ?? lang;
        return <Line key={`${id}:${pick(data.text, said)}`} data={data} lang={said} live={live} />;
      })}
    </ul>
  );
}
