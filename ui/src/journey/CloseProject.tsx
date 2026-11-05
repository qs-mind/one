// Close project: what is still open (Review comments, Deliverables not signed off) and the Review reports to open,
// the Lessons Learned one by one (Carry to Engineer Records, or Keep in project), then Archive. Nothing here blocks:
// with something open, Archive reads "Archive anyway", and the core keeps that choice in the audit trail. An
// archived project says "Archived, read-only" and offers Unarchive. The lessons come from a short Brief of the Lead
// QS, which the engineer starts with a press (it costs AI); a Confidential project shares none. A card still waiting
// in the chat counts as open.
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import { coreAnswer, coreLine, type Fix, send } from "../core";
import { primary, quiet, secondary } from "../firstlaunch/parts";
import { briefStarted } from "../import/importer";
import { count, fill, pick, t, type Text, texts, useLanguage } from "../i18n";
import { type Project, setCurrentProject } from "../records/project";
import { FixAction } from "../shell/FixAction";

type Lesson = { id: string; text: string; kind: string; carried: boolean };
type Closing = {
  open_comments: number;
  /** Deliverables that do not open or have a row with a problem, each with why. */
  broken?: { id: string; name: string; why: Text }[];
  unsigned: { id: string; name: string }[];
  reports: { id: string; name: string; revision: number }[];
  confidential: boolean;
  archived_at: string | null;
  lessons: Lesson[];
  /** Cards waiting for the engineer in the project chat (the core's count). */
  waiting?: number;
};

const proposed = new Set<string>(); // projects whose lessons Brief ran this session
const POLL_MS = 2000;
const FINDING_MAX_MS = 180_000;

export function CloseProject({
  project,
  briefRunning,
  onOpenDeliverable,
  onClose,
}: {
  project: Project;
  /** A Brief runs in the project chat: the lessons Brief, once it is started. */
  briefRunning: boolean;
  onOpenDeliverable: (id: string) => void;
  onClose: () => void;
}) {
  useLanguage();
  const title = useId();
  const id = encodeURIComponent(project.id);
  const [closing, setClosing] = useState<Closing>();
  const [failed, setFailed] = useState<Text>();
  const [failedFix, setFailedFix] = useState<Fix>(); // only the lessons' failure has one; any other failure clears it
  const fail = (line: Text | undefined) => {
    setFailed(line);
    setFailedFix(undefined);
  };
  const [finding, setFinding] = useState(false);
  const [kept, setKept] = useState<ReadonlySet<string>>(new Set());
  const [archiving, setArchiving] = useState(false);
  const [note, setNote] = useState<Text>();
  const sawBrief = useRef(false);

  const load = useCallback(async () => {
    const response = await api(`/projects/${id}/closing`).catch(() => undefined);
    if (!response?.ok) return void fail(await coreLine(response, texts.archiveFailed));
    const found = (await response.json()) as Closing;
    setClosing(found);
    return found;
  }, [id]);

  useEffect(() => void load(), [load, briefRunning]); // read again as a Brief starts or ends: what waits changes

  // The lessons are a step the engineer chooses: the Lead QS's Brief costs AI, so it starts only on a press.
  async function findLessons() {
    if (proposed.has(project.id)) return;
    proposed.add(project.id);
    fail(undefined);
    const response = await send(`/projects/${id}/lessons/propose`, "POST");
    if (response?.status === 202) {
      setFinding(true);
      briefStarted(project.id); // the Brief shows in the project chat like any other
    } else {
      proposed.delete(project.id); // not started (another Brief runs, or no AI yet): it can be asked again
      const answer = await coreAnswer(response, texts.lessonsNotStarted);
      setFailed(answer.line);
      setFailedFix(answer.fix); // no AI yet: AI settings
    }
  }

  useEffect(() => {
    // while the Lead QS picks lessons, they are read again every few seconds, and once more when its Brief ends
    if (!finding) return;
    if (briefRunning) sawBrief.current = true;
    else if (sawBrief.current) {
      sawBrief.current = false;
      setFinding(false);
      void load();
      return;
    }
    const poll = setInterval(() => void load(), POLL_MS);
    const stop = setTimeout(() => setFinding(false), FINDING_MAX_MS);
    return () => {
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [finding, briefRunning, load]);

  async function decide(lesson: Lesson, carry: boolean) {
    fail(undefined);
    const response = await send(`/projects/${id}/lessons/${encodeURIComponent(lesson.id)}`, "POST", { carry });
    if (!response?.ok) return fail(await coreLine(response, texts.archiveFailed));
    if (carry) void load();
    else setKept((now) => new Set(now).add(lesson.id)); // keeping it writes nothing
  }

  async function archive() {
    setArchiving(true);
    fail(undefined);
    setNote(undefined);
    const response = await send(`/projects/${id}/archive`, "POST");
    setArchiving(false);
    if (!response?.ok) return fail(await coreLine(response, texts.archiveFailed));
    const done = (await response.json()) as { archived_at: string; note: Text | null };
    if (done.note) setNote(done.note);
    setCurrentProject({ ...project, archived_at: done.archived_at });
    void load();
  }

  async function unarchive() {
    fail(undefined);
    const response = await send(`/projects/${id}/unarchive`, "POST");
    if (!response?.ok) return fail(await coreLine(response, texts.archiveFailed));
    setCurrentProject({ ...project, archived_at: null });
    void load();
  }

  const archived = closing ? closing.archived_at : (project.archived_at ?? null); // the core's answer, once read, wins
  const waiting = closing?.waiting ?? 0;
  const broken = closing?.broken ?? [];
  const blocked = broken.length > 0 || (closing?.unsigned.length ?? 0) > 0;
  const open = closing ? closing.open_comments > 0 || blocked || waiting > 0 : false;
  const lessons = closing?.lessons.filter((lesson) => !kept.has(lesson.id)) ?? [];

  return (
    <section aria-labelledby={title} className="flex flex-col gap-6 px-5 py-5">
      <div className="flex items-center justify-between gap-4">
        <h2 id={title} className="text-lg font-semibold">
          {fill(t("closeProjectTitle"), { name: "⁨" + project.name + "⁩" })}
        </h2>
        <button type="button" onClick={onClose} className={`${quiet} -me-3`}>
          {t("close")}
        </button>
      </div>

      {archived && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-stone px-4 py-3">
          <span className="font-semibold">{t("archivedReadOnly")}</span>
          <button type="button" onClick={() => void unarchive()} className={`${secondary} ms-auto`}>
            {t("unarchiveProject")}
          </button>
        </div>
      )}
      {note && (
        <div className="flex flex-col gap-2">
          <p role="status" className="text-copper">{pick(note)}</p>
          {/* the archive's only note: its final backup was not made, so Backup is the way to make it */}
          <FixAction fix="backup" />
        </div>
      )}

      {closing && (
        <>
          <div className="flex flex-col gap-3">
            {!archived && (blocked ? <p className="text-copper">{t("closeProjectBlockers")}</p> : <p className="text-slate">{t("closeProjectHelp")}</p>)}
            {!open && <p>{t("closeProjectAllClear")}</p>}
            {waiting > 0 && <p className="text-copper">{count("closeProjectWaiting", waiting)}</p>}
            {closing.open_comments > 0 && <p className="text-copper">{fill(t("closeProjectOpenComments"), { n: closing.open_comments })}</p>}
            {broken.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-copper">{t("closeProjectBroken")}</p>
                <ul className="flex flex-col">
                  {broken.map((d) => (
                    <li key={d.id}>
                      <button
                        type="button"
                        onClick={() => onOpenDeliverable(d.id)}
                        className="-ms-3 flex w-[calc(100%+12px)] flex-col items-start gap-0.5 rounded-md px-3 py-1.5 text-start hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
                      >
                        <span dir="auto" className="underline decoration-slate/40 underline-offset-4">
                          {d.name}
                        </span>
                        <span className="text-sm text-slate">{pick(d.why)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {closing.unsigned.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-copper">{t("closeProjectUnsigned")}</p>
                <ul className="flex flex-col gap-1 ps-4">
                  {closing.unsigned.map((d) => (
                    <li key={d.id} dir="auto">
                      {d.name}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {closing.reports.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="font-semibold">{t("closeProjectReports")}</p>
                <ul className="flex flex-col">
                  {closing.reports.map((r) => (
                    <li key={r.id}>
                      <button
                        type="button"
                        onClick={() => onOpenDeliverable(r.id)}
                        className="-ms-3 flex w-[calc(100%+12px)] items-baseline gap-2 rounded-md px-3 py-1.5 text-start hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
                      >
                        <span dir="auto" className="min-w-0 truncate underline decoration-slate/40 underline-offset-4">
                          {r.name}
                        </span>
                        <span className="shrink-0 text-sm text-slate">{fill(t("reviewRev"), { n: r.revision })}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-3">
            <h3 className="font-semibold">{t("lessonsTitle")}</h3>
            {closing.confidential ? (
              <p className="text-slate">{t("lessonsConfidential")}</p>
            ) : (
              <>
                {lessons.length > 0 && <p className="text-slate">{t("lessonsHelp")}</p>}
                {finding && <p role="status">{t("lessonsFinding")}</p>}
                {!finding && lessons.length === 0 && !archived && (
                  <div className="flex flex-col gap-2">
                    <p className="text-slate">{t("lessonsAsk")}</p>
                    <button type="button" onClick={() => void findLessons()} className={`${secondary} self-start`}>
                      {t("lessonsFind")}
                    </button>
                  </div>
                )}
                {!finding && lessons.length === 0 && archived && <p className="text-slate">{t("lessonsNone")}</p>}
                <ul className="flex flex-col gap-2">
                  {lessons.map((lesson) => (
                    <li key={lesson.id} className="flex flex-col gap-3 rounded-lg bg-stone px-4 py-3">
                      <p dir="auto">{lesson.text}</p>
                      {lesson.carried ? (
                        <p className="text-sm text-slate">{t("lessonCarried")}</p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          <button type="button" onClick={() => void decide(lesson, true)} className={secondary}>
                            {t("lessonCarry")}
                          </button>
                          <button type="button" onClick={() => void decide(lesson, false)} className={quiet}>
                            {t("lessonKeep")}
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          {!archived && (
            <div className="flex flex-col gap-2 border-t border-stone pt-5">
              <button type="button" disabled={archiving} onClick={() => void archive()} className={`${primary} self-start`}>
                {archiving ? t("archiveWorking") : open ? t("archiveAnyway") : t("archiveProject")}
              </button>
            </div>
          )}
        </>
      )}
      {failed && (
        <div className="flex flex-col gap-2">
          <p role="alert" className="text-copper">
            {pick(failed)}
          </p>
          <FixAction fix={failedFix} />
        </div>
      )}
    </section>
  );
}
