// Each folder import as it goes: the files being added, then what came in (added, the same file already there, kept
// but not read yet, too big, unreadable, zips opened), then the next step: the Lead QS reading the folder, or for old
// work, archived without the AI step, with "Understand it".
import { FileName } from "../ui/FileName";
import { fill, pick, t, useLanguage } from "../i18n";
import { primary, quiet } from "../firstlaunch/parts";
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
      <Names label={t("importUnreadable")} names={report.unreadable} />
      <Names label={t("importFailed")} names={report.failed} />
    </div>
  );
}

export function ImportReport({ job }: { job: Job }) {
  useLanguage();
  const adding = !job.report && !job.failed;
  const title = job.into
    ? fill(t("importIntoProject"), { name: "⁨" + job.name + "⁩" })
    : job.old
      ? job.name
      : fill(t("importNewProject"), { name: "⁨" + job.name + "⁩" });
  return (
    <section
      aria-label={title}
      data-import-report
      className="flex w-[min(400px,calc(100vw-32px))] flex-col gap-4 rounded-[14px] bg-paper px-5 py-4 shadow-[0_2px_12px_rgb(14_15_18/0.12)]"
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
          <div className="h-1.5 overflow-hidden rounded-full bg-stone">
            <div className="h-full rounded-full bg-ink transition-[width]" style={{ width: `${job.total ? (100 * job.done) / job.total : 0}%` }} />
          </div>
        </div>
      )}
      {job.failed && (
        <p role="alert" className="text-copper">
          {pick(job.failed)}
        </p>
      )}
      {job.report && <Counts report={job.report} />}
      {job.understanding === "started" && <p role="status">{t("importUnderstanding")}</p>}
      {job.understanding && job.understanding !== "started" && (
        <p role="alert" className="text-copper">
          {pick(job.understanding)}
        </p>
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
