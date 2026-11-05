// What ONE has to tell the engineer outside a Brief: each folder import's report and the one-time backup question.
// They are cards at the foot of the chat, just above the message box, where ONE's other words are: never over the
// work on the canvas, and read in the same place as the Brief an import starts. Many at once scroll in their own
// strip, so the conversation keeps its room. The shell opens a folded chat when a new one comes (App.tsx).
import { useRef } from "react";
import { useBackupAsk } from "../backup/ask";
import { BackupAsk } from "../backup/BackupPanel";
import { ImportReports } from "../import/ImportReport";
import { useImports } from "../import/importer";
import { useScrollEdges } from "../ui/useScrollEdges";

/** How many notices there are now. */
export function useNoticeCount(): number {
  return useImports().length + (useBackupAsk() ? 1 : 0);
}

export function Notices() {
  const strip = useRef<HTMLDivElement>(null);
  useScrollEdges(strip);
  const asking = useBackupAsk();
  if (!useNoticeCount()) return null;
  return (
    <div ref={strip} data-notices className="scroll-fade flex max-h-[45%] shrink-0 flex-col gap-3 overflow-y-auto px-5 pb-3 pt-1">
      <ImportReports />
      {asking && <BackupAsk />}
    </div>
  );
}
