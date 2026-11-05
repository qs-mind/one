// The project's status in the top bar: its stage, the submission date and the days left, the items left to price,
// the BOQ so far (with the Deliverable and Revision it comes from), the open comments. Each shows only when the core
// sends it; nothing is guessed. Two at most show in the bar, so it stays calm: the submission and the items left
// first, then the BOQ so far, the open comments, the stage; one too wide for the room is passed over for the next
// that fits. The rest fold into a "More status" button rather than being cut.
import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import type { DeliverableInfo, ProjectSources, ProjectStatus } from "../project/types";
import { count, fill, language, pick, t, useLanguage } from "../i18n";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { RollingNumber } from "../ui/RollingNumber";

const locale = () => (language() === "ar" ? "ar-EG-u-nu-latn" : "en-GB");

/** "19 Nov": the core sends the date as YYYY-MM-DD, a day on the engineer's calendar. */
function day(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return date;
  return new Intl.DateTimeFormat(locale(), { day: "numeric", month: "short" }).format(new Date(y, m - 1, d));
}

/** The value as the core sent it (a decimal string, never rounded through a float), in the page language. */
function money(value: string, currency: string, compact: boolean): string {
  const format = new Intl.NumberFormat(locale(), {
    style: "currency",
    currency,
    ...(compact ? { notation: "compact", maximumFractionDigits: 1 } : {}),
  });
  return format.format(value as unknown as number); // Intl reads a decimal string exactly
}

function statusLine(d: DeliverableInfo): string {
  if (d.status === "signed_off") return t("statusSignedOff");
  if (d.status === "checked") return fill(t("statusChecked"), { code: d.code ?? "" });
  return t("statusDraft");
}

const chip = "whitespace-nowrap rounded-lg px-3 py-1.5";
const GAP = 8; // gap-2
/** At most this many status items show in the bar; the rest are in More status. */
export const SHOWN_MOST = 2;
/** Which item stays longest when the bar is short: lower stays longer. */
const PRIORITY: Record<string, number> = { submission: 0, left: 1, boq: 2, comments: 3, stage: 4 };

/** Which of `widths` (in priority order) show in `room` px: all of them when they are two at most and fit; else at
 * most two that fit beside a `more` px button, in order, passing over one too wide for what is left. */
export function fitting(widths: readonly number[], room: number, more: number): number[] {
  const total = widths.reduce((sum, w) => sum + w, 0) + GAP * Math.max(0, widths.length - 1);
  if (widths.length <= SHOWN_MOST && total <= room) return widths.map((_, i) => i);
  const shown: number[] = [];
  let used = more;
  for (const [i, w] of widths.entries()) {
    if (shown.length === SHOWN_MOST) break;
    if (used + GAP + w > room) continue;
    used += GAP + w;
    shown.push(i);
  }
  return shown;
}

export function StatusStrip({
  status,
  sources,
  stacked = false,
}: {
  status: ProjectStatus;
  sources?: ProjectSources;
  /** Folded into the narrow layout's Status popover: one item per line. */
  stacked?: boolean;
}) {
  const lang = useLanguage();
  const [boqFrom, setBoqFrom] = useState<DeliverableInfo | null>(null);
  const boq = status.boq_value;
  const items: { key: string; node: ReactNode }[] = [];

  if (status.stage) items.push({ key: "stage", node: <span className={`${chip} bg-stone text-ink`}>{pick(status.stage)}</span> });
  if (status.submission_date)
    items.push({
      key: "submission",
      node: (
        <span className={chip}>
          {status.days_left === undefined ? (
            <bdi>{day(status.submission_date)}</bdi>
          ) : (
            fill(t("submission"), { date: day(status.submission_date), days: status.days_left })
          )}
        </span>
      ),
    });
  if (boq?.items !== undefined && boq.priced !== undefined && boq.priced < boq.items)
    items.push({ key: "left", node: <span className={chip}>{count("itemsLeft", boq.items - boq.priced)}</span> });
  if (boq)
    items.push({
      key: "boq",
      node: (
        <Popover
          onOpenChange={(open) => {
            if (open && sources)
              void sources
                .deliverables()
                .then((list) => setBoqFrom(list.find((d) => d.id === boq.deliverable_id) ?? null))
                .catch(() => setBoqFrom(null));
          }}
        >
          <PopoverTrigger className={`${chip} hover:bg-stone hover:text-ink`}>
            {t("boqSoFar")}{" "}
            <bdi dir="ltr" className="text-ink">
              {/* rolls when the core's total changes; another BOQ, or the other language, shows still */}
              <RollingNumber key={`${boq.deliverable_id} ${lang}`} text={money(boq.value, boq.currency, true)} />
            </bdi>
            {boq.items !== undefined && (
              <span className="text-slate">
                {" · "}
                {boq.of ? count("boqItemsOf", boq.of, { done: boq.items }) : count("boqItems", boq.items)}
              </span>
            )}
            {boq.sample && <span className="ms-1 text-copper">({t("sampleData")})</span>}
          </PopoverTrigger>
          <PopoverContent className="flex flex-col gap-1">
            <bdi dir="ltr" className="font-semibold">
              {money(boq.value, boq.currency, false)}
            </bdi>
            {boqFrom && (
              <span dir="auto" lang={boqFrom.language}>
                {fill(t("boqFrom"), { title: boqFrom.title })}
              </span>
            )}
            <span>{boq.revision === null ? t("notIssued") : fill(t("reviewRev"), { n: boq.revision })}</span>
            {boqFrom && <span>{statusLine(boqFrom)}</span>}
          </PopoverContent>
        </Popover>
      ),
    });
  if (status.open_comments !== undefined && status.open_comments > 0)
    items.push({
      key: "comments",
      node: <span className={`${chip} text-copper`}>{count("openComments", status.open_comments)}</span>,
    });

  // each item keeps its place in the strip, laid out even while folded (invisible, out of the flow), so its width is
  // always known; then how many fit
  const box = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState<ReadonlySet<string> | null>(null); // null: all
  // with something folded the strip keeps room for More status at least: a long name never squeezes it out of sight
  const [floor, setFloor] = useState(0);
  const signature = items.map((item) => item.key).join() + lang + JSON.stringify(status);
  useLayoutEffect(() => {
    if (stacked) return;
    const el = box.current;
    if (!el) return;
    const update = () => {
      const room = el.clientWidth; // the strip is the one item in the top bar that shrinks
      const width = (key: string) => el.querySelector<HTMLElement>(`[data-status="${key}"]`)?.offsetWidth ?? 0;
      const order = [...items].sort((a, b) => PRIORITY[a.key]! - PRIORITY[b.key]!);
      const widths = order.map((item) => width(item.key));
      if (!widths.some(Boolean)) return setShown(null); // nothing laid out (no layout engine): show them all
      const more = width("more");
      const fit = fitting(widths, room, more);
      const all = fit.length >= items.length;
      setShown(all ? null : new Set(fit.map((i) => order[i]!.key)));
      setFloor(all ? 0 : more);
    };
    update();
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(update);
    observer?.observe(el);
    document.fonts?.addEventListener("loadingdone", update); // the widths change when the fonts come
    return () => {
      observer?.disconnect();
      document.fonts?.removeEventListener("loadingdone", update);
    };
  }, [signature, stacked]);

  if (stacked)
    return <div className="flex min-w-0 flex-col items-start gap-2 text-slate">{items.map((item) => <span key={item.key}>{item.node}</span>)}</div>;

  const folded = shown ? items.filter((item) => !shown.has(item.key)) : [];
  const away = "invisible absolute start-0 top-0";
  return (
    <div ref={box} style={floor ? { minWidth: floor } : undefined} className="relative flex min-w-0 flex-1 items-center gap-2 overflow-hidden text-slate">
      {items.map((item) => {
        const hidden = shown !== null && !shown.has(item.key);
        return (
          <span key={item.key} data-status={item.key} aria-hidden={hidden || undefined} inert={hidden} className={`flex shrink-0 ${hidden ? away : ""}`}>
            {item.node}
          </span>
        );
      })}
      <Popover>
        <PopoverTrigger
          data-status="more"
          aria-hidden={folded.length ? undefined : true}
          tabIndex={folded.length ? undefined : -1}
          className={`${chip} shrink-0 hover:bg-stone hover:text-ink ${folded.length ? "" : away}`}
        >
          {t("moreStatus")}
        </PopoverTrigger>
        <PopoverContent className="flex flex-col items-start gap-2">
          {folded.map((item) => (
            <span key={item.key}>{item.node}</span>
          ))}
        </PopoverContent>
      </Popover>
    </div>
  );
}
