// The project's status in the top bar: its stage, the submission date and the days left, the BOQ so far (with the
// Deliverable and Revision it comes from), the open comments. Each shows only when the core sends it; nothing is
// guessed.
import { useState } from "react";
import type { DeliverableInfo, ProjectSources, ProjectStatus } from "../canvas/types";
import { count, fill, language, pick, t, useLanguage } from "../i18n";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";

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

const chip = "whitespace-nowrap rounded-md px-2 py-0.5";

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
  useLanguage();
  const [boqFrom, setBoqFrom] = useState<DeliverableInfo | null>(null);
  const boq = status.boq_value;

  return (
    <div className={`flex min-w-0 gap-2 overflow-hidden text-slate ${stacked ? "flex-col items-start" : "items-center"}`}>
      {status.stage && <span className={`${chip} bg-stone text-ink`}>{pick(status.stage)}</span>}
      {status.submission_date && (
        <span className={chip}>
          {status.days_left === undefined ? (
            <bdi>{day(status.submission_date)}</bdi>
          ) : (
            fill(t("submission"), { date: day(status.submission_date), days: status.days_left })
          )}
        </span>
      )}
      {boq && (
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
            {t("boqSoFar")} <bdi dir="ltr" className="text-ink">{money(boq.value, boq.currency, true)}</bdi>
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
      )}
      {status.open_comments !== undefined && status.open_comments > 0 && (
        <span className={`${chip} text-copper`}>{count("openComments", status.open_comments)}</span>
      )}
    </div>
  );
}
