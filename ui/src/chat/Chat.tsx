// The conversation with the Lead QS, as a list: the engineer's messages (with the canvas selection they were sent
// with) and each Brief's reply with its Progress Line, Coordination Room, cards, costs, Review codes and Deliverable
// cards. The shell owns the chat itself (ui/src/shell/useChats.ts) and its composer, the command bar.
import { useEffect, useRef } from "react";
import type { SelectionItem } from "../canvas/types";
import { DeliverableCard } from "../deliverables/DeliverableCard";
import { fill, pick, t, type Text, useLanguage } from "../i18n";
import { HandOffCards } from "../shell/HandOffCard";
import type { ChatState } from "../shell/useChats";
import { textOf } from "../shell/useChats";
import { ApprovalCard } from "./parts/ApprovalCard";
import { ContinueBriefs } from "./parts/ContinueBriefs";
import { CoordinationRoom } from "./parts/CoordinationRoom";
import { CostNotice } from "./parts/CostNotice";
import { ProgressLine } from "./parts/ProgressLine";
import { ReviewBadge } from "./parts/ReviewBadge";
import { type OnePart, partsOf } from "./parts/types";
import { Reply } from "./Reply";

// The core sends a model error as an {en, ar} pair in the error text; any other failure gets the plain line.
function errorLine(error: Error): string {
  try {
    const text = JSON.parse(error.message) as Partial<Text>;
    if (typeof text.en === "string" && typeof text.ar === "string") return pick(text as Text);
  } catch {
    // not from the core
  }
  return t("chatError");
}

/** "Selected: BOQ pricing, rows 3/01–3/04", or "3 selected". The name keeps its own direction (an Arabic title on
 * an English page). */
export function SelectionText({ items }: { items: readonly SelectionItem[] }) {
  if (items.length !== 1) return <span>{fill(t("selectedMany"), { n: items.length })}</span>;
  const [item] = items;
  const name = item!.label ? fill(t("selectedRange"), { title: item!.title, label: item!.label }) : item!.title;
  const [before, after] = t("selected").split("{name}");
  return (
    <span>
      {before}
      <bdi dir="auto">{name}</bdi>
      {after}
    </span>
  );
}

function BriefReply({ parts, projectId, onOpenDeliverable }: { parts: OnePart[] } & Omit<ChatLogProps, "chat" | "label">) {
  const text = textOf(parts);
  return (
    <div className="flex flex-col gap-3">
      <ProgressLine items={partsOf(parts, "progress")} />
      <CoordinationRoom messages={partsOf(parts, "team")} />
      {text && <Reply text={text} unsourced={partsOf(parts, "unsourced").flatMap((part) => part.data.values)} />}
      {partsOf(parts, "card").map((card) => (
        // the top bar's "Waiting for you" goes to the first card still waiting
        <div key={card.id} data-waiting={card.data.status === "pending" || card.data.status === undefined || undefined}>
          <ApprovalCard id={card.id} card={card.data} />
        </div>
      ))}
      {partsOf(parts, "cost").map((cost) => (
        <CostNotice key={cost.id} cost={cost.data} />
      ))}
      {partsOf(parts, "review").map((review) => (
        <ReviewBadge key={review.id} review={review.data} />
      ))}
      {projectId &&
        onOpenDeliverable &&
        partsOf(parts, "deliverable").map((part) => (
          <DeliverableCard key={part.id} projectId={projectId} id={part.data.id} onOpen={onOpenDeliverable} />
        ))}
      <HandOffCards parts={parts} />
    </div>
  );
}

export type ChatLogProps = {
  chat: ChatState;
  /** The log's accessible name: the project chat or the General chat. */
  label: string;
  projectId?: string;
  /** A Deliverable card's Open. */
  onOpenDeliverable?: (id: string) => void;
};

/** The messages, as a polite log the engineer can scroll from the keyboard (it is focusable). */
export function ChatLog({ chat, label, projectId, onOpenDeliverable, className = "" }: ChatLogProps & { className?: string }) {
  useLanguage();
  const { messages, status, error, failed } = chat;
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo?.({ top: ref.current.scrollHeight });
  }, [messages]);

  return (
    <div className={`flex min-h-0 flex-col ${className}`}>
      <ContinueBriefs onContinued={chat.continued} />
      <div
        ref={ref}
        role="log"
        aria-label={label}
        tabIndex={0}
        data-region-start
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4 focus-visible:outline-2 focus-visible:outline-ink"
      >
        <ol className="flex flex-col gap-4">
          {messages.length === 0 && <li className="text-slate">{t("empty")}</li>}
          {messages.map((message) =>
            message.role === "user" ? (
              <li key={message.id} className="max-w-[85%] self-end rounded-lg bg-stone px-3 py-2">
                {message.metadata?.steering && <p className="text-slate">{t("steering")}</p>}
                {message.metadata?.selection?.length ? (
                  <p className="mb-1 w-fit rounded-md border border-ink/10 bg-paper px-2 text-slate">
                    <SelectionText items={message.metadata.selection} />
                  </p>
                ) : null}
                <p dir="auto" className="whitespace-pre-wrap">
                  {textOf(message.parts)}
                </p>
              </li>
            ) : (
              <li key={message.id}>
                <BriefReply parts={message.parts} projectId={projectId} onOpenDeliverable={onOpenDeliverable} />
              </li>
            ),
          )}
          {status === "submitted" && <li className="text-slate">{t("thinking")}</li>}
          {error && (
            <li role="alert" className="text-copper">
              {errorLine(error)}
            </li>
          )}
          {failed && (
            <li role="alert" className="text-copper">
              {pick(failed)}
            </li>
          )}
        </ol>
      </div>
    </div>
  );
}
