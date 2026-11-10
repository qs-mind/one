// The tender's conversation column: U3's thread centred at its measure, a tender with no plan yet asking for one
// under it, and the message box. In the document view the same column is the narrow thread beside the document.
import { useRef } from "react";
import type { Schemas } from "@/api/client";
import { Composer } from "@/conversation/Composer";
import { Thread } from "@/conversation/Thread";
import { notify } from "@/design/notify";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";
import { NoPlan } from "./NoPlan";
import type { TenderData, useTender } from "./useTender";
import type { useThread } from "./useThread";

type TenderThreadProps = {
  data: TenderData;
  actions: ReturnType<typeof useTender>["actions"];
  thread: ReturnType<typeof useThread>;
  /** The narrow thread beside a document: the Lead's name above it, as Document.dc.html draws. */
  narrow?: boolean;
};

const LEAD = "lead-qs";

export function TenderThread({ data, actions, thread, narrow = false }: TenderThreadProps) {
  const t = useText();
  const box = useRef<HTMLDivElement>(null);
  const row = data.view?.tender;
  const lead = data.members.find((m) => m.id === LEAD);
  const leadName = lead ? t(lead.name) : "Lead QS";
  const archived = row?.state === "archived";

  // A refused write says the core's words; one that got no answer says it did not go through.
  const said = async (write: Promise<Schemas["Text"] | null>) => {
    const refused = await write.catch(() => t(texts.failed));
    if (refused) notify(typeof refused === "string" ? refused : t(refused));
  };
  const discuss = () => box.current?.querySelector("textarea")?.focus();

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      {narrow && (
        <h2 className="text-xs text-muted-foreground">
          <bdi dir={textDir(leadName)}>{leadName}</bdi>
        </h2>
      )}
      <div className="min-h-0 flex-1">
        <Thread
          messages={thread.messages}
          leadName={leadName}
          plan={data.plan ?? null}
          findings={data.findings}
          onApprovePlan={(version) => void said(actions.approvePlan(version))}
          onDiscussPlan={discuss}
          onPlanChange={(changeId, accept) => void said(actions.answerChange(changeId, accept))}
          onDecide={(findingId, choice) => void said(actions.decide(findingId, choice))}
        />
      </div>
      {data.plan === null && !archived && (
        <NoPlan onRequest={actions.requestPlan} blocked={row?.blocked ?? null} />
      )}
      <div ref={box} data-tender-composer className={narrow ? "" : "mx-auto w-full max-w-(--measure)"}>
        {archived && <p className="pb-2 text-muted-foreground">{t(texts.archived)}</p>}
        {!archived && row?.blocked && <p className="pb-2 text-muted-foreground">{t(row.blocked.reason)}</p>}
        <Composer onSend={thread.send} onSteer={thread.steer} activity={thread.activity} disabled={archived} />
      </div>
    </div>
  );
}
