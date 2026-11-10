// A tender's thread (ai-elements Conversation): the engineer's messages, the Lead's replies with what they placed
// (the plan card, decision cards, a stage's sign-off block, the cards a running Brief waits on), and the live line at
// the end. Pointer parts draw from the state the screen holds; only the last copy of a part is live, an earlier one
// is one line (3.1, rules 1 to 4). Cards wait one at a time. A failed Brief, or a message the core refused, says why.
import { Fragment, type ReactNode, useState } from "react";
import { cards as words } from "@/texts/cards";
import { conversation } from "@/texts/conversation";
import { textDir } from "@/texts/language";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { Conversation, ConversationContent, ConversationEmptyState, ConversationScrollButton } from "./ai/conversation";
import { Message, MessageContent } from "./ai/message";
import { CardPart } from "./CardPart";
import { type Choice, DecisionCard, fromFinding, oneAtATime } from "./DecisionCard";
import { LeadMessage } from "./LeadMessage";
import { LiveLine, type LogStep } from "./LiveLine";
import {
  briefState,
  cardsOf,
  type DataPart,
  failedBrief,
  type Finding,
  isData,
  isLive,
  liveProgress,
  livePlaces,
  type Source,
  type TenderPlan,
  type ThreadMessage,
  textOf,
  workLog,
} from "./parts";
import { PlanCard } from "./PlanCard";
import { SourceLinks } from "./SourceLinks";
import { StageCard } from "./StageCard";
import { UnfinishedCard } from "./UnfinishedCard";

export type ThreadProps = {
  messages: readonly ThreadMessage[];
  /** The Lead's name as the core gives it (Member.title). */
  leadName: string;
  plan: TenderPlan | null;
  findings: readonly Finding[];
  /** The work log; built from the running reply when left out. */
  log?: readonly LogStep[];
  /** A member's name, for the team's messages in the work log. */
  memberName?: (id: string) => TextPair | undefined;
  /** Work cut off that waits for the engineer (its Brief ids): drawn at the end. */
  unfinished?: readonly string[];
  /** Why the last message got no answer, in the screen's language. */
  error?: string | null;
  /** Nothing can be answered (an archived tender). */
  disabled?: boolean;
  onApprovePlan: (version: number) => void;
  onDiscussPlan: () => void;
  onPlanChange: (changeId: string, accept: boolean) => void;
  onDecide: (findingId: string, choice: Choice) => void;
  onSignOff?: (stageId: string, version: number) => void;
  onNotes?: () => void;
  onContinue?: (briefId: string) => void;
  onLeave?: (briefId: string) => void;
  onOpenSource?: (source: Source) => void;
};

function EngineerBubble({ text }: { text: string }) {
  return (
    <Message from="user">
      <MessageContent>
        <p dir={textDir(text)}>{text}</p>
      </MessageContent>
    </Message>
  );
}

const Pointer = ({ children }: { children: ReactNode }) => <p className="text-xs text-muted-foreground">{children}</p>;
const POINTERS = ["steer", "plan", "finding", "stage", "card"] as const;

export function Thread(props: ThreadProps) {
  const { messages, leadName, plan, findings, onOpenSource, disabled = false } = props;
  const t = useText();
  const [answered, setAnswered] = useState<ReadonlySet<string>>(new Set());
  const live = livePlaces(messages);
  const state = briefState(messages);
  const decisions = oneAtATime(findings.flatMap((f) => fromFinding(f, t.lang) ?? []));
  const decisionOf = (id: string) => decisions.find((d) => d.id === id);
  const pointed = new Set(messages.flatMap((m) => m.parts.flatMap((p) => ("id" in p && p.id ? [`${p.type}:${p.id}`] : []))));
  const lastReply = messages.findLast((m) => m.role === "assistant");
  const failed = failedBrief(messages);
  // One card waits at a time: the first the core still waits on that was not answered here.
  const openCard = cardsOf(messages).find((c) => (c.data.status ?? "pending") === "pending" && !answered.has(c.id))?.id;

  const who = (id: string): TextPair => (id === "engineer" ? words.you : id === "team" ? words.team : (props.memberName?.(id) ?? words.member));
  const log =
    props.log ??
    workLog(messages).map((entry): LogStep =>
      "step" in entry ? entry.step : { agent: who(entry.room.from_id), to: who(entry.room.to_id), said: entry.room.text, done: true },
    );

  const planCard = (version: number) => (
    <PlanCard plan={plan} version={version} onApprove={props.onApprovePlan} onDiscuss={props.onDiscussPlan} onChange={props.onPlanChange} onOpenSource={onOpenSource} />
  );
  const decisionCard = (id: string) => {
    const decision = decisionOf(id);
    return decision ? (
      <DecisionCard decision={decision} asker={leadName} onChoose={(choice) => props.onDecide(id, choice)} onOpenSource={onOpenSource} />
    ) : null;
  };
  const stageCard = (id: string) => (
    <StageCard
      stageId={id}
      plan={plan}
      disabled={disabled}
      onSignOff={(stage, version) => props.onSignOff?.(stage, version)}
      onNotes={() => (props.onNotes ?? props.onDiscussPlan)()}
    />
  );
  const card = (part: DataPart<"card">, id: string) => {
    const pending = (part.data.status ?? "pending") === "pending" && !answered.has(id);
    if (pending && id !== openCard)
      return <Pointer>{t(conversation.queued, { title: t(part.data.title) })}</Pointer>;
    return <CardPart id={id} card={part.data} disabled={disabled} onOpenSource={onOpenSource} onAnswered={(done) => setAnswered((was) => new Set(was).add(done))} />;
  };

  /** A reply, in the order it came: its words, the engineer's steers and what it placed, each at its place; the
   *  name once above, the sources once below. */
  function reply(message: ThreadMessage) {
    const out: ReactNode[] = [];
    let text = "";
    let sources: readonly Source[] = [];
    const streaming = message === lastReply && (state === "running" || state === "queued");
    const flush = (key: string) => {
      if (text) out.push(<LeadMessage key={key} text={text} streaming={streaming} />);
      text = "";
    };
    message.parts.forEach((part, index) => {
      const key = `${message.id}:${index}`;
      if (part.type === "text") return void (text += part.text);
      if (isData(part, "sources")) return void (sources = (part as DataPart<"sources">).data.sources);
      if (!POINTERS.some((kind) => isData(part, kind))) return;
      flush(`${key}:words`);
      const id = "id" in part ? (part.id ?? "") : "";
      let drawn: ReactNode;
      if (isData(part, "steer")) drawn = <EngineerBubble text={(part as DataPart<"steer">).data.text} />;
      else if (isData(part, "card")) drawn = card(part as DataPart<"card">, id);
      else if (!isLive(live, message, index)) drawn = <Pointer>{t(conversation.laterPart)}</Pointer>;
      else if (isData(part, "plan")) drawn = planCard((part as DataPart<"plan">).data.version);
      else if (isData(part, "stage")) drawn = stageCard((part as DataPart<"stage">).data.stage_id);
      else drawn = decisionCard((part as DataPart<"finding">).data.finding_id);
      out.push(
        <div key={key} data-part={id || undefined} className="flex flex-col">
          {drawn}
        </div>,
      );
    });
    flush(`${message.id}:end`);
    if (message === lastReply && failed?.data.step) out.push(<Pointer key="failed">{`${t(words.workFailed)}: ${t(failed.data.step)}`}</Pointer>);
    if (out.length === 0 && sources.length === 0) return null;
    return (
      <div className="flex flex-col gap-3">
        <span className="text-xs text-muted-foreground">
          <bdi dir={textDir(leadName)}>{leadName}</bdi>
        </span>
        {out}
        <SourceLinks sources={sources} onOpen={onOpenSource} />
      </div>
    );
  }

  // Rule 4: what waits with no part in the thread is drawn at its end, from the route alone.
  const planWaits = plan && (plan.status === "proposed" || plan.change) && !pointed.has(`data-plan:${plan.id}`);
  const unpointed = decisions.filter((d) => d.state !== "settled" && !pointed.has(`data-finding:${d.id}`));
  const stagesWait = (plan?.stages ?? []).filter((s) => s.status === "waiting_engineer" && !pointed.has(`data-stage:${s.id}`));
  const unfinished = props.unfinished ?? [];
  const waitsAtEnd = planWaits || unpointed.length > 0 || stagesWait.length > 0 || unfinished.length > 0;

  return (
    <Conversation aria-label={t(conversation.threadLabel)} className="size-full">
      <ConversationContent className="mx-auto w-full max-w-(--measure)">
        {messages.length === 0 && !waitsAtEnd ? (
          <ConversationEmptyState title={t(conversation.emptyTitle)} description={t(conversation.emptyBody)} />
        ) : (
          messages.map((message) => {
            if (message.role === "assistant") return <Fragment key={message.id}>{reply(message)}</Fragment>;
            if (message.metadata?.by === "one") return <Pointer key={message.id}>{t(conversation.byOne)}</Pointer>;
            return <EngineerBubble key={message.id} text={textOf(message)} />;
          })
        )}
        {planWaits && <div data-part={plan.id}>{planCard(plan.version)}</div>}
        {unpointed.map((d) => (
          <div key={d.id} data-part={d.id}>
            {decisionCard(d.id)}
          </div>
        ))}
        {stagesWait.map((s) => (
          <div key={s.id} data-part={s.id}>
            {stageCard(s.id)}
          </div>
        ))}
        {unfinished.map((id) => (
          <div key={id} data-part={id}>
            <UnfinishedCard briefId={id} disabled={disabled} onContinue={(b) => props.onContinue?.(b)} onLeave={(b) => props.onLeave?.(b)} />
          </div>
        ))}
        {props.error && (
          <p role="alert" dir={textDir(props.error)} className="text-xs text-muted-foreground">
            {props.error}
          </p>
        )}
        <LiveLine progress={liveProgress(messages)} log={log} />
      </ConversationContent>
      <ConversationScrollButton label={t(conversation.scrollToEnd)} />
    </Conversation>
  );
}
