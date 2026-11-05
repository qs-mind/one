// The conversation with the Lead QS, as a list: the engineer's messages (with the canvas selection they were sent
// with) and each Brief's reply with its Progress Line, Coordination Room, cards, costs, Review codes and Deliverable
// cards. The shell owns the chat itself (ui/src/shell/useChats.ts) and its composer, the command bar.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { SelectionItem } from "../canvas/types";
import { DeliverableCard } from "../deliverables/DeliverableCard";
import { fill, type Language, language, languageOf, pick, t, type Text, useLanguage } from "../i18n";
import { UnderstoodCard } from "../import/UnderstoodCard";
import { HandOffCards } from "../shell/HandOffCard";
import type { ChatState } from "../shell/useChats";
import { textOf } from "../shell/useChats";
import { ApprovalCard, CARD_ANSWERED } from "./parts/ApprovalCard";
import { ContinueBriefs } from "./parts/ContinueBriefs";
import { CoordinationRoom } from "./parts/CoordinationRoom";
import { CostNotice } from "./parts/CostNotice";
import { ProgressLine } from "./parts/ProgressLine";
import { ReviewBadge } from "./parts/ReviewBadge";
import { type OnePart, partsOf } from "./parts/types";
import { BidiText } from "./bidi";
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

/** The engineer's own message: each line a block that finds its own direction, the other script's runs isolated. */
function OwnText({ text }: { text: string }) {
  return text.split("\n").map((line, i) => (
    <p key={i} dir="auto" className="min-h-[1lh] whitespace-pre-wrap">
      <BidiText text={line} />
    </p>
  ));
}

function BriefReply({
  parts,
  lang,
  projectId,
  onOpenDeliverable,
}: { parts: OnePart[]; lang: Language } & Omit<ChatLogProps, "chat" | "label">) {
  const text = textOf(parts);
  const progress = partsOf(parts, "progress");
  // the Brief's own language: the core's word for it, else the engineer's message's
  const said = progress.find((item) => item.data.lang)?.data.lang ?? lang;
  return (
    <div className="flex flex-col gap-4">
      <ProgressLine items={progress} lang={said} />
      <CoordinationRoom messages={partsOf(parts, "team")} />
      {text && <Reply text={text} unsourced={partsOf(parts, "unsourced").flatMap((part) => part.data.values)} />}
      {partsOf(parts, "card").map((card) => (
        // the top bar's "Waiting for you" goes to the first card still waiting
        <div
          key={card.id}
          data-card={card.id}
          data-waiting={card.data.status === "pending" || card.data.status === undefined || undefined}
        >
          <ApprovalCard id={card.id} card={card.data} lang={said} />
        </div>
      ))}
      {partsOf(parts, "understood").map((part) => (
        <UnderstoodCard key={part.id} projectId={part.data.project_id} />
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

/** How near the end (px) still counts as reading the newest message. */
const NEAR_END = 48;

/** The cards still waiting for the engineer, by id. */
const waitingCards = (messages: ChatState["messages"]) =>
  messages.flatMap((message) =>
    partsOf(message.parts, "card")
      .filter((card) => card.data.status === "pending" || card.data.status === undefined)
      .map((card) => card.id),
  );

/** The messages, as a polite log the engineer can scroll from the keyboard (it is focusable). New content keeps the
 * log at its end while the engineer reads there; scrolled up, a "New below" button shows instead. A card that comes
 * to wait for the engineer is always brought into view. */
export function ChatLog({ chat, label, projectId, onOpenDeliverable, className = "" }: ChatLogProps & { className?: string }) {
  useLanguage();
  const { messages, status, error, failed } = chat;
  const ref = useRef<HTMLDivElement>(null);
  const atEnd = useRef(true);
  const seen = useRef<Set<string> | null>(null);
  const [below, setBelow] = useState(false);

  const toEnd = () => {
    ref.current?.scrollTo?.({ top: ref.current.scrollHeight });
    atEnd.current = true;
    setBelow(false);
  };

  useEffect(() => {
    // an answered card: the engineer is done here, so the chat follows the Brief again, to its next words
    const log = ref.current;
    const follow = () => requestAnimationFrame(toEnd);
    log?.addEventListener(CARD_ANSWERED, follow);
    return () => log?.removeEventListener(CARD_ANSWERED, follow);
  }, []);

  useLayoutEffect(() => {
    const log = ref.current;
    if (!log) return;
    const waiting = waitingCards(messages);
    const fresh = seen.current ? waiting.filter((id) => !seen.current!.has(id)) : [];
    seen.current = new Set(waiting);
    if (atEnd.current) toEnd();
    else if (messages.length) setBelow(true);
    if (fresh.length) {
      const card = [...log.querySelectorAll<HTMLElement>("[data-card]")].find((el) => el.dataset.card === fresh[0]);
      card?.scrollIntoView?.({ block: "nearest" });
    }
  }, [messages, status]);

  return (
    <div className={`flex min-h-0 flex-col ${className}`}>
      <ContinueBriefs onContinued={chat.continued} />
      <div
        ref={ref}
        role="log"
        aria-label={label}
        tabIndex={0}
        data-region-start
        onScroll={(event) => {
          const log = event.currentTarget;
          atEnd.current = log.scrollHeight - log.scrollTop - log.clientHeight <= NEAR_END;
          if (atEnd.current) setBelow(false);
        }}
        className="relative min-h-0 flex-1 overflow-y-auto px-5 py-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink"
      >
        <ol className="flex flex-col gap-6">
          {messages.length === 0 && <li className="text-slate">{t("empty")}</li>}
          {messages.map((message, index) =>
            message.role === "user" ? (
              <li key={message.id} className="max-w-[85%] self-end rounded-2xl bg-stone px-4 py-3">
                {message.metadata?.steering && <p className="text-slate">{t("steering")}</p>}
                {message.metadata?.selection?.length ? (
                  <p className="mb-2 w-fit rounded-lg bg-paper px-3 py-0.5 text-sm text-slate">
                    <SelectionText items={message.metadata.selection} />
                  </p>
                ) : null}
                <OwnText text={textOf(message.parts)} />
              </li>
            ) : (
              <li key={message.id}>
                <BriefReply
                  parts={message.parts}
                  lang={briefLanguage(messages, index)}
                  projectId={projectId}
                  onOpenDeliverable={onOpenDeliverable}
                />
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
        {below && (
          <div className="pointer-events-none sticky bottom-0 flex justify-center pt-2">
            <button
              type="button"
              onClick={toEnd}
              className="pointer-events-auto rounded-full border border-ink/[0.08] bg-paper px-4 py-1.5 shadow-[0_2px_12px_rgb(14_15_18/0.08)] hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
            >
              {t("newBelow")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** The language of the Brief whose reply is at `index`: the one of the engineer's message that started it (a
 * steering message does not change it); the page's when there is none. */
function briefLanguage(messages: ChatState["messages"], index: number): Language {
  const asked = messages.slice(0, index).findLast((m) => m.role === "user" && !m.metadata?.steering);
  return asked ? languageOf(textOf(asked.parts)) : language();
}
