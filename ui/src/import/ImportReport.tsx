// Each folder import as it goes: the files being added, then what came in (added, the same file already there, kept
// but not read yet, too big, unreadable, zips opened), then the next step: the Lead QS reading the folder, or for old
// work, archived without the AI step, with "Understand it".
import { useEffect, useRef, useState } from "react";
import { FoldMark, summaryLook } from "../chat/parts/Fold";
import { useActivity } from "../shell/chatActivity";
import { FileName } from "../ui/FileName";
import { ProgressBar } from "../ui/ProgressBar";
import { WorkDots } from "../ui/WorkDots";
import { fill, pick, t, useLanguage } from "../i18n";
import { primary, quiet } from "../firstlaunch/parts";
import { FixAction } from "../shell/FixAction";
import { dismiss, type Job, understandIt, useImports } from "./importer";
import type { Report } from "./walk";

export function ImportReports() {
  const jobs = useImports();
  if (!jobs.length) return null;
  return (
    <div className="flex flex-col gap-3">
      {jobs.map((job) => (
        <ImportReport key={job.key} job={job} />
      ))}
    </div>
  );
}

function Names({ label, names }: { label: string; names: string[] }) {
  if (!names.length) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-copper">{label}</p>
      <ul className="flex max-h-32 flex-col gap-0.5 overflow-y-auto ps-4 text-sm">
        {names.map((name, i) => (
          <li key={`${name}-${i}`} className="flex">
            <FileName name={name} fit />
          </li>
        ))}
      </ul>
    </div>
  );
}

function Counts({ report }: { report: Report }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="font-semibold">{t("importReportTitle")}</h3>
      <ul className="flex flex-col gap-0.5">
        <li>{fill(t("importAdded"), { n: report.added })}</li>
        {report.duplicates > 0 && <li>{fill(t("importDuplicates"), { n: report.duplicates })}</li>}
        {report.notRead > 0 && <li>{fill(t("importNotRead"), { n: report.notRead })}</li>}
        {report.zips > 0 && <li>{fill(t("importZips"), { n: report.zips })}</li>}
      </ul>
      <Names label={t("importTooBig")} names={report.tooBig} />
      <Names label={t("importLocked")} names={report.locked} />
      <Names label={t("importUnreadable")} names={report.unreadable} />
      <Names label={t("importEmpty")} names={report.empty} />
      <Names label={t("importFailed")} names={report.failed} />
    </div>
  );
}

/** One line of what came in, for the folded summary. */
function CountsLine({ report }: { report: Report }) {
  const parts = [
    fill(t("importAdded"), { n: report.added }),
    report.duplicates > 0 && fill(t("importDuplicates"), { n: report.duplicates }),
    report.notRead > 0 && fill(t("importNotRead"), { n: report.notRead }),
    report.zips > 0 && fill(t("importZips"), { n: report.zips }),
  ].filter(Boolean);
  const missed = report.tooBig.length + report.locked.length + report.unreadable.length + report.empty.length + report.failed.length;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-slate">{parts.join(" · ")}</p>
      {missed > 0 && (
        <details>
          <summary className={`${summaryLook} text-copper`}>
            <FoldMark open={false} />
            {t("importMissed")}
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            <Names label={t("importTooBig")} names={report.tooBig} />
            <Names label={t("importLocked")} names={report.locked} />
            <Names label={t("importUnreadable")} names={report.unreadable} />
            <Names label={t("importEmpty")} names={report.empty} />
            <Names label={t("importFailed")} names={report.failed} />
          </div>
        </details>
      )}
    </div>
  );
}

type Reading = "reading" | "waiting" | "ended";
const LATE_MS = 6000; // a Brief never seen working by then has ended already (a short one, between two looks)

/** Where the "I understood this" Brief is, from the activity across chats: reading, waiting on its card, or ended. */
function useReading(job: Job): Reading | undefined {
  const list = useActivity();
  const seen = useRef(false);
  const [late, setLate] = useState(false);
  const following = job.understanding === "started" && Boolean(job.briefId);
  useEffect(() => {
    if (!following) return;
    const timer = setTimeout(() => setLate(true), LATE_MS);
    return () => clearTimeout(timer);
  }, [following]);
  if (job.understanding !== "started") return undefined;
  if (!job.briefId) return "reading";
  const now = list.find((chat) => chat.brief_id === job.briefId)?.state;
  if (now === "working" || now === "waiting") seen.current = true;
  if (now === "working") return "reading";
  if (now === "waiting") return "waiting";
  if (now || seen.current || late) return "ended";
  return "reading";
}

export function ImportReport({ job }: { job: Job }) {
  useLanguage();
  const reading = useReading(job);
  const adding = !job.report && !job.failed;
  // once the Lead QS is no longer reading, the summary folds to a line: the "I understood this" card stays in sight
  const folded = Boolean(job.report) && (reading === "waiting" || reading === "ended");
  const title = job.into
    ? fill(t("importIntoProject"), { name: "⁨" + job.name + "⁩" })
    : job.old
      ? job.name
      : fill(t("importNewProject"), { name: "⁨" + job.name + "⁩" });
  return (
    <section
      aria-label={title}
      data-import-report
      className={`flex w-full flex-col rounded-[14px] border border-ink/[0.08] bg-paper ${folded ? "gap-1.5 px-4 py-2.5" : "gap-4 px-5 py-4"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <h2 dir="auto" className="min-w-0 font-semibold break-words">
          {title}
        </h2>
        {!adding && (
          <button type="button" onClick={() => dismiss(job.key)} className={`${quiet} -me-3 -mt-1.5 shrink-0`}>
            {t("close")}
          </button>
        )}
      </div>
      {adding && (
        <div className="flex flex-col gap-2" role="status">
          <p>{fill(t("importUploading"), { done: job.done, total: job.total })}</p>
          <ProgressBar done={job.done} total={job.total} />
        </div>
      )}
      {job.failed && (
        <p role="alert" className="text-copper">
          {pick(job.failed)}
        </p>
      )}
      {job.report && (folded ? <CountsLine report={job.report} /> : <Counts report={job.report} />)}
      {reading === "reading" && (
        <p role="status" className="flex items-baseline gap-2">
          {t("importUnderstanding")}
          <WorkDots />
        </p>
      )}
      {reading === "waiting" && <p role="status">{t("importUnderstoodWaits")}</p>}
      {reading === "ended" && <p role="status" className="text-slate">{t("importUnderstoodDone")}</p>}
      {job.understanding && job.understanding !== "started" && (
        <div className="flex flex-col gap-2">
          <p role="alert" className="text-copper">
            {pick(job.understanding)}
          </p>
          <FixAction fix={job.understandingFix} />
        </div>
      )}
      {job.old && job.archived && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-slate">{t("importOldArchived")}</p>
          <button type="button" onClick={() => void understandIt(job.key)} className={primary}>
            {t("importUnderstandIt")}
          </button>
        </div>
      )}
    </section>
  );
}
