// A tender's thread (ai-elements Conversation): the engineer's messages, the Lead's replies with what they placed
// (the plan card, decision cards), and the live line at the end. Pointer parts draw from the state the screen
// holds; only the last copy of a part is live, an earlier one is one line (3.1, rules 1 to 4).
import { Fragment, type ReactNode } from "react";
import { conversation } from "@/texts/conversation";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import { Conversation, ConversationContent, ConversationEmptyState, ConversationScrollButton } from "./ai/conversation";
import { Message, MessageContent } from "./ai/message";
import { type Choice, DecisionCard, fromFinding, oneAtATime } from "./DecisionCard";
import { LeadMessage } from "./LeadMessage";
import { LiveLine, type LogStep } from "./LiveLine";
import { briefState, type DataPart, type Finding, isData, isLive, liveProgress, livePlaces, type Source, type TenderPlan, type ThreadMessage, textOf } from "./parts";
import { PlanCard } from "./PlanCard";
import { SourceLinks } from "./SourceLinks";

export type ThreadProps = {
  messages: readonly ThreadMessage[];
  /** The Lead's name as the core gives it (Member.title). */
  leadName: string;
  plan: TenderPlan | null;
  findings: readonly Finding[];
  log?: readonly LogStep[];
  onApprovePlan: (version: number) => void;
  onDiscussPlan: () => void;
  onPlanChange: (changeId: string, accept: boolean) => void;
  onDecide: (findingId: string, choice: Choice) => void;
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

export function Thread(props: ThreadProps) {
  const { messages, leadName, plan, findings, log, onOpenSource } = props;
  const t = useText();
  const live = livePlaces(messages);
  const state = briefState(messages);
  const decisions = oneAtATime(findings.flatMap((f) => fromFinding(f, t.lang) ?? []));
  const decisionOf = (id: string) => decisions.find((d) => d.id === id);
  const pointed = new Set(messages.flatMap((m) => m.parts.flatMap((p) => ("id" in p && p.id ? [`${p.type}:${p.id}`] : []))));
  const lastReply = messages.findLast((m) => m.role === "assistant");

  const planCard = (version: number) => (
    <PlanCard
      plan={plan}
      version={version}
      onApprove={props.onApprovePlan}
      onDiscuss={props.onDiscussPlan}
      onChange={props.onPlanChange}
    />
  );
  const decisionCard = (id: string) => {
    const decision = decisionOf(id);
    return decision ? (
      <DecisionCard
        decision={decision}
        asker={leadName}
        onChoose={(choice) => props.onDecide(id, choice)}
        onOpenSource={onOpenSource}
      />
    ) : null;
  };

  /** A reply, in the order it came: its words, the engineer's steers and the cards it placed, each at its place;
   *  the name once above, the sources once below. */
  function reply(message: ThreadMessage) {
    const out: ReactNode[] = [];
    let words = "";
    let sources: readonly Source[] = [];
    const streaming = message === lastReply && (state === "running" || state === "queued");
    const flush = (key: string) => {
      if (words) out.push(<LeadMessage key={key} text={words} streaming={streaming} />);
      words = "";
    };
    message.parts.forEach((part, index) => {
      const key = `${message.id}:${index}`;
      if (part.type === "text") return void (words += part.text);
      if (isData(part, "sources")) return void (sources = (part as DataPart<"sources">).data.sources);
      if (!isData(part, "steer") && !isData(part, "plan") && !isData(part, "finding")) return;
      flush(`${key}:words`);
      if (isData(part, "steer")) out.push(<EngineerBubble key={key} text={(part as DataPart<"steer">).data.text} />);
      else if (!isLive(live, message, index)) out.push(<Pointer key={key}>{t(conversation.laterPart)}</Pointer>);
      else if (isData(part, "plan")) out.push(<Fragment key={key}>{planCard((part as DataPart<"plan">).data.version)}</Fragment>);
      else out.push(<Fragment key={key}>{decisionCard((part as DataPart<"finding">).data.finding_id)}</Fragment>);
    });
    flush(`${message.id}:end`);
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

  return (
    <Conversation aria-label={t(conversation.threadLabel)} className="size-full">
      <ConversationContent className="mx-auto w-full max-w-(--measure)">
        {messages.length === 0 && !planWaits && unpointed.length === 0 ? (
          <ConversationEmptyState title={t(conversation.emptyTitle)} description={t(conversation.emptyBody)} />
        ) : (
          messages.map((message) => {
            if (message.role === "assistant") return <Fragment key={message.id}>{reply(message)}</Fragment>;
            if (message.metadata?.by === "one") return <Pointer key={message.id}>{t(conversation.byOne)}</Pointer>;
            return <EngineerBubble key={message.id} text={textOf(message)} />;
          })
        )}
        {planWaits && planCard(plan.version)}
        {unpointed.map((d) => (
          <Fragment key={d.id}>{decisionCard(d.id)}</Fragment>
        ))}
        <LiveLine progress={liveProgress(messages)} log={log} />
      </ConversationContent>
      <ConversationScrollButton label={t(conversation.scrollToEnd)} />
    </Conversation>
  );
}
