// The tender's conversation column: U3's thread centred at its measure, a tender with no plan yet asking for one
// under it, and the message box. In the document view the same column is the narrow thread beside the document.
// What the engineer drops on the box goes into the tender before the words go to the Lead.
import { useRef } from "react";
import type { Schemas } from "@/api/client";
import { continueBrief, leaveBrief } from "@/api/existing";
import type { Source } from "@/conversation/parts";
import { Composer, type ComposerMessage } from "@/conversation/Composer";
import { Thread } from "@/conversation/Thread";
import { notify } from "@/design/notify";
import { cards } from "@/texts/cards";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";
import { addDropped } from "./addDropped";
import { NoPlan } from "./NoPlan";
import type { TenderData, useTender } from "./useTender";
import type { useThread } from "./useThread";

type TenderThreadProps = {
  data: TenderData;
  actions: ReturnType<typeof useTender>["actions"];
  thread: ReturnType<typeof useThread>;
  /** The narrow thread beside a document: the Lead's name above it, as Document.dc.html draws. */
  narrow?: boolean;
  onOpenSource: (source: Source) => void;
};

const LEAD = "lead-qs";

export function TenderThread({ data, actions, thread, narrow = false, onOpenSource }: TenderThreadProps) {
  const t = useText();
  const box = useRef<HTMLDivElement>(null);
  const row = data.view?.tender;
  const projectId = row?.project_id ?? "";
  const lead = data.members.find((m) => m.id === LEAD);
  const leadName = t(lead ? lead.name : cards.leadName);
  const archived = row?.state === "archived";
  const unfinished = (data.view?.waiting ?? []).filter((item) => item.kind === "unfinished").map((item) => item.id);

  // A refused write says the core's words; one that got no answer says it did not go through.
  const said = async (write: Promise<Schemas["Text"] | null>) => {
    const refused = await write.catch(() => t(texts.failed));
    if (refused) notify(typeof refused === "string" ? refused : t(refused));
  };
  const discuss = () => box.current?.querySelector("textarea")?.focus();
  const brief = (call: (id: string) => ReturnType<typeof continueBrief>, then?: () => void) => async (id: string) => {
    const got = await call(id);
    if (got.error !== undefined) notify(t(got.error ?? texts.failed));
    else then?.();
  };

  /** The dropped files go in first; then the words, if any. */
  async function withFiles(message: ComposerMessage, words: (message: ComposerMessage) => unknown) {
    if (message.attachments.length) {
      const added = await addDropped(projectId, message.attachments);
      notify(added === null ? t(cards.filesNotIn) : t.plural(cards.filesIn, added));
    }
    if (message.text.trim()) await words(message);
  }

  const refusal = thread.refused ? t(thread.refused.words ?? cards.noAnswer) : null;
  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      {narrow && (
        <h2 className="text-xs text-muted-foreground">
          <bdi dir={textDir(leadName)}>{leadName}</bdi>
        </h2>
      )}
      {/* a choice button and a source link wrap their words rather than run past a narrow card (the shared
          Button neither shrinks nor wraps) */}
      <div className="min-h-0 flex-1 [&_[data-decision]_button]:shrink [&_button.link]:shrink [&_button.link]:text-start [&_button.link]:whitespace-normal">
        <Thread
          messages={thread.messages}
          leadName={leadName}
          plan={data.plan ?? null}
          findings={data.findings}
          memberName={(id) => data.members.find((m) => m.id === id)?.name}
          unfinished={archived ? [] : unfinished}
          error={refusal}
          disabled={archived}
          onApprovePlan={(version) => void said(actions.approvePlan(version))}
          onDiscussPlan={discuss}
          onPlanChange={(changeId, accept) => void said(actions.answerChange(changeId, accept))}
          onDecide={(findingId, choice) => void said(actions.decide(findingId, choice))}
          onSignOff={(stageId, version) => void said(actions.signOffStage(stageId, version))}
          onNotes={discuss}
          onContinue={(id) => void brief(continueBrief, thread.resume)(id)}
          onLeave={(id) => void brief(leaveBrief)(id)}
          onOpenSource={onOpenSource}
        />
      </div>
      {data.plan === null && !archived && <NoPlan onRequest={actions.requestPlan} blocked={row?.blocked ?? null} />}
      <div ref={box} data-tender-composer className={narrow ? "" : "mx-auto w-full max-w-(--measure)"}>
        {archived && <p className="pb-2 text-muted-foreground">{t(texts.archived)}</p>}
        {!archived && row?.blocked && <p className="pb-2 text-muted-foreground">{t(row.blocked.reason)}</p>}
        <Composer
          onSend={(message) => void withFiles(message, thread.send)}
          onSteer={(message) => withFiles(message, thread.steer)}
          activity={thread.activity}
          disabled={archived || Boolean(row?.blocked)}
        />
      </div>
    </div>
  );
}
