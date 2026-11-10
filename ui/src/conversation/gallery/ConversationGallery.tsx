// The conversation parts' gallery page (dev only, /next.html#/conversation): the whole thread with its message box,
// then each part in its states, in the language of the address. Every value is the contract's sample data.
import { useState } from "react";
import { Demo, State } from "@/design/gallery/parts";
import { notify } from "@/design/notify";
import { conversationGallery as g } from "@/texts/design/conversation";
import { useText } from "@/texts/useText";
import { Composer, type ComposerMessage } from "../Composer";
import { type Decision, DecisionCard, fromFinding } from "../DecisionCard";
import { LeadMessage } from "../LeadMessage";
import { LiveLine } from "../LiveLine";
import type { Finding, TenderPlan, ThreadMessage } from "../parts";
import { PlanCard } from "../PlanCard";
import { Thread } from "../Thread";
import * as s from "./samples";

const now = () => new Date().toISOString().replace("Z", "000+00:00");

/** The thread as a tender shows it: the answers change the samples in memory, nothing leaves the page. */
function LiveThread() {
  const t = useText();
  const [messages, setMessages] = useState<ThreadMessage[]>(() => s.sampleThread(t.lang));
  const [plan, setPlan] = useState<TenderPlan>(s.planProposed);
  const [findings, setFindings] = useState<Finding[]>(s.findings);
  const send = ({ text }: ComposerMessage) =>
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", parts: [{ type: "text", text }] }]);
  return (
    <div className="flex h-180 w-full max-w-(--measure) flex-col gap-4">
      <div className="min-h-0 flex-1">
        <Thread
          messages={messages}
          leadName={t(s.leadName)}
          plan={plan}
          findings={findings}
          log={s.log}
          onApprovePlan={() => setPlan({ ...plan, status: "approved", approved_at: now() })}
          onDiscussPlan={() => notify(t(g.planCard))}
          onPlanChange={() => {}}
          onDecide={(id, choice) =>
            setFindings((prev) =>
              prev.map((f) => (f.id === id ? { ...f, status: "settled", chosen: choice, settled_at: now() } : f)),
            )
          }
        />
      </div>
      <Composer onSend={send} />
    </div>
  );
}

export function ConversationGallery() {
  const t = useText();
  const lead = t(s.leadName);
  const decision = (finding: Finding) => fromFinding(finding, t.lang)!;
  const card = (d: Decision) => <DecisionCard decision={d} asker={lead} onChoose={(c) => notify(t(g.sent, { text: d.options[c] }))} />;
  const sent = ({ text }: ComposerMessage) => notify(t(g.sent, { text }));
  return (
    <div className="flex flex-col gap-18">
      <p className="max-w-155 text-lg text-muted-foreground">{t(g.intro)}</p>
      <Demo id="thread" title="Thread">
        <LiveThread />
      </Demo>
      <Demo id="lead-message" title="LeadMessage">
        <State name={t(g.short)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <LeadMessage name={lead} text={t(g.leadShort)} />
        </State>
        <State name={t(g.folded)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <LeadMessage name={lead} text={t(g.leadRead)} sources={s.raised.sources} />
        </State>
      </Demo>
      <Demo id="live-line" title="LiveLine">
        <State name={t(g.working)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <LiveLine progress={{ agent: g.agent, text: g.reading }} log={s.log} />
        </State>
      </Demo>
      <Demo id="decision-card" title="DecisionCard">
        <State name={t(g.waiting)} className="flex w-full max-w-(--measure) flex-col gap-2">
          {card({ ...decision(s.paidFinding), hold: { why: "paid", options: [0] } })}
        </State>
        <State name={t(g.queuedState)} className="flex w-full max-w-(--measure) flex-col gap-2">
          {card(decision(s.queued))}
        </State>
        <State name={t(g.settled)} className="flex w-full max-w-(--measure) flex-col gap-2">
          {card(decision(s.settled))}
        </State>
      </Demo>
      <Demo id="plan-card" title="PlanCard">
        <State name={t(g.proposed)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <PlanCard plan={s.planProposed} version={1} onApprove={() => {}} onDiscuss={() => {}} onChange={() => {}} />
        </State>
        <State name={t(g.withChange)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <PlanCard plan={s.planWithChange} version={s.planWithChange.version} onApprove={() => {}} onDiscuss={() => {}} onChange={() => {}} />
        </State>
        <State name={t(g.replacedState)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <PlanCard plan={{ ...s.planProposed, version: 2 }} version={1} onApprove={() => {}} onDiscuss={() => {}} onChange={() => {}} />
        </State>
      </Demo>
      <Demo id="composer" title="Composer">
        <State name={t(g.idle)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <Composer onSend={sent} />
        </State>
        <State name={t(g.working)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <Composer onSend={sent} activity="working" />
        </State>
        <State name={t(g.held)} className="flex w-full max-w-(--measure) flex-col gap-2">
          <Composer onSend={sent} activity="held" />
        </State>
      </Demo>
    </div>
  );
}
