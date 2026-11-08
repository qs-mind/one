// The Progress Line and the work log. It is in the Brief's language (the engineer's, for that Brief), not the page's:
// an Arabic Brief in the English page shows Arabic progress, as its reply is.
//
// With the core's work log (data-worklog: each step with its real start and end), it is an honest log. While the
// Brief runs, Thinking shimmers over every step so far; a step still running is a chip with its own timer, counting
// the real time since the core said it began, and three dots fading beside it; no fill bar, no guess. When the Brief
// ends, Thinking settles to its real time and step count ("Worked for 2m 5s · 6 steps"). The steps stay folded
// throughout (Kareem, 8 Nov: the chat shows the conversation, not the work): while it runs only the step running now
// shows beside Thinking, and a click opens them all. Nothing here runs on a timer but the chip's clock, and only while that step runs.
// With reduced motion there is no shimmer, no fade and no ticking clock: just the words.
//
// A Brief stored before the work log came shows the older line: one per agent, its latest words, updated in place.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { count, dir, fill, type Language, pick, t, useLanguage } from "../../i18n";
import { AutoHeight } from "../../ui/AutoHeight";
import { DUR, play, useReducedMotion } from "../../ui/motion";
import { WorkDots } from "../../ui/WorkDots";
import { FoldMark } from "./Fold";
import type { ProgressData, WorklogData, WorkStep } from "./types";

/** The app's numerals: Latin digits in both languages. */
const locale = (lang: Language) => (lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB");

/** A Brief's whole time in words: "42s", "2m 5s" (whole minutes past ten), "1h 5m"; «دقيقتين و5 ثواني». */
export function duration(ms: number, lang: Language): string {
  const s = Math.floor(Math.max(0, ms) / 1000);
  const both = (a: string, b: string) => fill(t("durationAnd", lang), { a, b });
  if (s < 1) return t("underASecond", lang);
  if (s < 60) return count("seconds", s, {}, lang);
  const m = Math.floor(s / 60);
  if (m < 60) {
    const minutes = count("minutes", m, {}, lang);
    return s % 60 && m < 10 ? both(minutes, count("seconds", s % 60, {}, lang)) : minutes;
  }
  const hours = count("hours", Math.floor(m / 60), {}, lang);
  return m % 60 ? both(hours, count("minutes", m % 60, {}, lang)) : hours;
}

/** A step's time, short: "1.2 s" under a minute, then "1m 05s"; «1.2 ث», «1 د 05 ث». */
export function tick(ms: number, lang: Language): string {
  const s = Math.max(0, ms) / 1000;
  if (s < 60) {
    const tenths = new Intl.NumberFormat(locale(lang), { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return fill(t("tickSeconds", lang), { s: tenths.format(Math.floor(s * 10) / 10) });
  }
  const whole = Math.floor(s);
  return fill(t("tickMinutes", lang), { m: Math.floor(whole / 60), s: String(whole % 60).padStart(2, "0") });
}

const span = (from: string, to: string) => Date.parse(to) - Date.parse(from);

/** Now, again every 100 ms while `on`: the running chip's clock. */
function useNow(on: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, [on]);
  return now;
}

/** A running step: what it does (its words carry the file's name) and how long it has run. */
function RunningChip({ step, lang }: { step: WorkStep; lang: Language }) {
  const reduced = useReducedMotion();
  const now = useNow(!reduced);
  return (
    <span data-running className="inline-flex max-w-full items-baseline gap-1.5 rounded-full bg-stone px-2.5 py-0.5 text-ink">
      <span dir="auto" className="min-w-0 truncate">
        {pick(step.text, lang)}
      </span>
      {!reduced && (
        <>
          {" "}
          <span className="tabular-nums text-slate">· {tick(now - Date.parse(step.at), lang)}</span>
          <WorkDots />
        </>
      )}
    </span>
  );
}

/** A line of the log: one step, or the same step done again and again in a row (`times`), its time the sum. */
type Shown = { step: WorkStep; times: number; took: number; named: boolean };

/** The steps as lines: the agent's name once at the head of each run of its steps (said again to a screen reader on
 * every line, so each still reads whole), and the same finished step repeated in a row folded into one line, "×2". */
export function lines(steps: readonly WorkStep[]): Shown[] {
  const out: Shown[] = [];
  const same = (a: WorkStep, b: WorkStep) => a.agent.en === b.agent.en && a.text.en === b.text.en && a.text.ar === b.text.ar;
  for (const step of steps) {
    const last = out.at(-1);
    const took = step.until ? span(step.at, step.until) : 0;
    if (last && last.step.until !== null && step.until !== null && same(last.step, step)) {
      last.times += 1;
      last.took += took;
      continue;
    }
    out.push({ step, times: 1, took, named: !last || last.step.agent.en !== step.agent.en });
  }
  return out;
}

/** One line of the log; rises in (150 ms) when it arrives while the Brief is live. */
function Step({ line: { step, times, took, named }, lang, live }: { line: Shown; lang: Language; live: boolean }) {
  const ref = useRef<HTMLLIElement>(null);
  useLayoutEffect(() => {
    if (live && ref.current) void play(ref.current, [{ opacity: 0, transform: "translateY(0.5em)" }, { opacity: 1, transform: "none" }], DUR.short);
  }, []); // on arrival only
  return (
    <li ref={ref} className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
      {named ? (
        <span data-agent className="basis-full font-semibold text-ink">
          {pick(step.agent, lang)}
        </span>
      ) : (
        <span className="sr-only">{pick(step.agent, lang)}</span>
      )}{" "}
      {live && step.until === null ? (
        <RunningChip step={step} lang={lang} />
      ) : (
        <span dir="auto">{pick(step.text, lang)}</span>
      )}
      {times > 1 && (
        <bdi dir="ltr" className="tabular-nums">
          ×{times}
        </bdi>
      )}
      {took >= 100 && ( // under a tenth of a second there is nothing honest to show
        <>
          {" "}
          <span className="tabular-nums">· {tick(took, lang)}</span>
        </>
      )}
    </li>
  );
}

/** Each line's React key: its time and agent, then how many lines before it had both (two steps can start in the same
 * millisecond), so a line keeps its key as the log grows. */
function keys(shown: Shown[]): string[] {
  const seen = new Map<string, number>();
  return shown.map(({ step }) => {
    const base = `${step.at}|${step.agent.en}`;
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    return `${base}|${n}`;
  });
}

function Steps({ steps, lang, live }: { steps: WorkStep[]; lang: Language; live: boolean }) {
  const shown = lines(steps);
  const key = keys(shown);
  return (
    <ul aria-label={t("workSteps", lang)} aria-live={live ? "polite" : undefined} className="flex flex-col gap-1">
      {shown.map((line, i) => (
        <Step key={key[i]} line={line} lang={lang} live={live} />
      ))}
    </ul>
  );
}

/** The work log of one Brief. */
function WorkLog({ log, lang, live }: { log: WorklogData; lang: Language; live: boolean }) {
  const reduced = useReducedMotion();
  const [open, setOpen] = useState(false);
  const header = useRef<HTMLDivElement>(null);
  const ended = log.ended !== null;
  const steps = log.steps.length;
  const running = live && !ended ? log.steps.findLast((step) => step.until === null) : undefined;
  const time = ended ? duration(span(log.started, log.ended!), lang) : "";
  // with no steps there is nothing to open: just the time, as words, not a button
  const settled = ended && steps ? fill(t("workedFor", lang), { time, steps: count("steps", steps, {}, lang) }) : undefined;
  const was = useRef(ended);
  useLayoutEffect(() => {
    // Thinking settles to the real time: the new words fade in where the shimmer was (opacity only)
    if (ended && !was.current && header.current) void play(header.current, [{ opacity: 0 }, { opacity: 1 }], DUR.base);
    was.current = ended;
  }, [ended]);
  return (
    <div lang={lang} dir={dir(lang)} className="flex flex-col gap-1 text-slate">
      <div ref={header}>
        {settled ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="flex items-baseline gap-2 text-start hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
          >
            <FoldMark open={open} lang={lang} />
            <span className="tabular-nums">{settled}</span>
          </button>
        ) : ended ? (
          <span className="tabular-nums">{fill(t("workedForOnly", lang), { time })}</span>
        ) : (
          (live || steps > 0) && (
            // while it works: one line, Thinking and the step running now; the steps open only on a click
            <span className="flex min-w-0 flex-wrap items-baseline gap-2">
              <button
                type="button"
                aria-expanded={open}
                disabled={!steps}
                onClick={() => setOpen(!open)}
                className="flex items-baseline gap-2 text-start hover:text-ink focus-visible:outline-2 focus-visible:outline-ink disabled:hover:text-slate"
              >
                {steps > 0 && <FoldMark open={open} lang={lang} />}
                <span className={reduced || !live ? "text-slate" : "shimmer"}>{t("thinking", lang)}</span>
              </button>
              {!open && running && <RunningChip step={running} lang={lang} />}
            </span>
          )
        )}
      </div>
      <AutoHeight>{open && log.steps.length > 0 && <Steps steps={log.steps} lang={lang} live={live && !ended} />}</AutoHeight>
    </div>
  );
}

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

export function ProgressLine({
  items,
  worklog,
  lang,
  live = false,
}: {
  items: { id: string; data: ProgressData }[];
  /** The core's work log for this Brief; without it, the older per-agent line. */
  worklog?: WorklogData;
  lang?: Language;
  live?: boolean;
}) {
  const page = useLanguage();
  if (worklog) return <WorkLog log={worklog} lang={lang ?? page} live={live} />;
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
