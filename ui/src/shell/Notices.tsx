// What ONE has to tell the engineer outside a Brief: each folder import's report, the one-time backup question, and
// one quiet line when another chat's work finished, failed or started waiting («خلص الشغل في «test» · افتح»).
// They are cards at the foot of the chat, just above the message box, where ONE's other words are: never over the
// work on the canvas, and read in the same place as the Brief an import starts. Many at once scroll in their own
// strip, so the conversation keeps its room. The shell opens a folded chat when a new import report or question
// comes (App.tsx); the other chat's line never does: the top bar's mark says it too.
import { useRef, useState } from "react";
import { useBackupAsk } from "../backup/ask";
import { BackupAsk } from "../backup/BackupPanel";
import { quiet } from "../firstlaunch/parts";
import { fill, pick, t, type Text, useLanguage } from "../i18n";
import { ImportReports } from "../import/ImportReport";
import { useImports } from "../import/importer";
import { openChat } from "../records/ProjectPicker";
import { useScrollEdges } from "../ui/useScrollEdges";
import { ActivityMark } from "./ActivityMark";
import { type ActivityNotice, dismissNotice, GENERAL, useActivityNotice } from "./chatActivity";

/** How many notices there are now (the other chat's line is not counted: it never opens the chat). */
export function useNoticeCount(): number {
  return useImports().length + (useBackupAsk() ? 1 : 0);
}

const NOTICE_LINE = { done: "activityNoticeDone", failed: "activityNoticeFailed", waiting: "activityNoticeWaiting" } as const;

/** The notice's words, also the system notification's. */
export function noticeLine(notice: ActivityNotice): string {
  const name = notice.chatId === GENERAL ? t("generalChat") : (notice.name ?? "");
  return fill(t(NOTICE_LINE[notice.state]), { name: "⁨" + name + "⁩" });
}

function OtherChat({ notice }: { notice: ActivityNotice }) {
  useLanguage();
  const [failed, setFailed] = useState<Text>();
  const line = noticeLine(notice);
  return (
    <section
      aria-label={line}
      data-activity-notice
      className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-[14px] border border-ink/[0.08] bg-paper px-4 py-1.5"
    >
      <ActivityMark state={notice.state} />
      <p role="status" dir="auto" className="min-w-0 flex-1 break-words">
        {line}
      </p>
      <button
        type="button"
        className={`${quiet} -my-1 text-ink`}
        onClick={async () => {
          setFailed(await openChat(notice.chatId));
        }}
      >
        {t("activityOpen")}
      </button>
      <button type="button" className={`${quiet} -my-1 -me-3`} onClick={dismissNotice}>
        {t("close")}
      </button>
      {failed && (
        <p role="alert" className="w-full text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}

export function Notices() {
  const strip = useRef<HTMLDivElement>(null);
  useScrollEdges(strip);
  const asking = useBackupAsk();
  const other = useActivityNotice();
  if (!useNoticeCount() && !other) return null;
  return (
    <div ref={strip} data-notices className="scroll-fade flex max-h-[45%] shrink-0 flex-col gap-3 overflow-y-auto px-5 pb-3 pt-1">
      {other && <OtherChat key={`${other.chatId}:${other.state}`} notice={other} />}
      <ImportReports />
      {asking && <BackupAsk />}
    </div>
  );
}
