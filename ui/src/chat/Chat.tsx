// The conversation with the Lead QS, as a list: the engineer's messages (with the canvas selection they were sent
// with) and each Brief's reply with its Progress Line, Coordination Room, cards, costs, Review codes and Deliverable
// cards. The shell owns the chat itself (ui/src/shell/useChats.ts) and its composer, the command bar.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { SelectionItem } from "../canvas/types";
import { type Fix, fixOf } from "../core";
import { DeliverableCard } from "../deliverables/DeliverableCard";
import { dir, fill, type Language, language, languageOf, pick, t, type Text, useLanguage } from "../i18n";
import { UnderstoodCard } from "../import/UnderstoodCard";
import { FixAction } from "../shell/FixAction";
import { HandOffCards } from "../shell/HandOffCard";
import type { ChatState } from "../shell/useChats";
import { textOf } from "../shell/useChats";
import { FileName } from "../ui/FileName";
import { DUR, play, useReducedMotion } from "../ui/motion";
import { CARD_ANSWERED, useApprovalQueue } from "./parts/ApprovalCard";
import { ContinueBriefs } from "./parts/ContinueBriefs";
import { CoordinationRoom } from "./parts/CoordinationRoom";
import { CostNotice } from "./parts/CostNotice";
import { FactsLine, withoutRedone } from "./parts/FactsLine";
import { ProgressLine } from "./parts/ProgressLine";
import { ReviewBadge } from "./parts/ReviewBadge";
import { type OnePart, partsOf } from "./parts/types";
import { ViewPart } from "./parts/view/ViewPart";
import { BidiText, baseDirection } from "./bidi";
import { Reply } from "./Reply";
import { takeSentFrom } from "./sent";
import { useScrollEdges } from "../ui/useScrollEdges";

// The core sends a model error as an {en, ar} pair in the error text, with the `fix` the chat can offer (a refused
// key: Open AI settings); any other failure gets the plain line.
function errorLine(error: Error): { line: string; fix?: Fix } {
  try {
    // the stream's error chunk ({en, ar, fix}), or a refused request's body ({error: {en, ar}, fix})
    const said = JSON.parse(error.message) as Partial<Text> & { error?: Partial<Text>; fix?: unknown };
    const text = said.error ?? said;
    if (typeof text.en === "string" && typeof text.ar === "string") {
      return { line: pick({ en: text.en, ar: text.ar }), fix: fixOf(said.fix) };
    }
  } catch {
    // not from the core
  }
  return { line: t("chatError") };
}

/** The chat's error line, and the button to where it is fixed. */
function ErrorLine({ error }: { error: Error }) {
  const { line, fix } = errorLine(error);
  return (
    <li role="alert" className="flex flex-col gap-2 text-copper">
      <p>{line}</p>
      <FixAction fix={fix} />
    </li>
  );
}

/** "Selected: BOQ pricing, rows 3/01–3/04", or "3 selected". The name keeps its own direction (an Arabic title on
 * an English page) and to one line: a long one ends in «…», its full name in a Tip. */
export function SelectionText({ items }: { items: readonly SelectionItem[] }) {
  if (items.length !== 1) return <span>{fill(t("selectedMany"), { n: items.length })}</span>;
  const [item] = items;
  const [before, after] = t("selected").split("{name}");
  const range = t("selectedRange"); // "{title}, {label}": the words between the two
  const between = range.slice(range.indexOf("{title}") + "{title}".length, range.indexOf("{label}"));
  return (
    <span className="inline-flex min-w-0 max-w-full items-baseline whitespace-pre">
      {before && <span className="shrink-0">{before}</span>}
      <FileName name={item!.title} fit />
      {item!.label && (
        <span className="shrink-0">
          {between}
          <bdi dir="auto">{item!.label}</bdi>
        </span>
      )}
      {after && <span className="shrink-0">{after}</span>}
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

const failedReply = (parts: OnePart[]) => partsOf(parts, "status").at(-1)?.data.state === "failed";

function BriefReply({
  parts,
  lang,
  live,
  projectId,
  onOpenDeliverable,
}: { parts: OnePart[]; lang: Language; live: boolean } & Omit<ChatLogProps, "chat" | "label">) {
  const text = withoutRedone(textOf(parts), partsOf(parts, "redo").at(-1)?.data);
  const progress = partsOf(parts, "progress");
  // the Brief's own language: the core's word for it, else the engineer's message's
  const said = progress.find((item) => item.data.lang)?.data.lang ?? lang;
  // one card open at a time; the top bar's "Waiting for you" goes to it (data-waiting)
  const cardAt = useApprovalQueue(partsOf(parts, "card"), said);
  const firstText = parts.findIndex((part) => part.type === "text");
  // the words, the views, the cards and the "I understood this" card each in its own place, in the order they came
  const inOrder = parts.map((part, index) => {
    if (part.type === "text")
      return index === firstText && text ? (
        <Reply
          key="text"
          text={text}
          unsourced={partsOf(parts, "unsourced").flatMap((one) => one.data.values)}
          sourced={Object.assign({}, ...partsOf(parts, "sourced").map((one) => one.data.numbers))}
          projectId={projectId}
        />
      ) : null;
    const [one] = partsOf([part], "view");
    if (one) return <ViewPart key={`view:${one.id}`} view={one.data} projectId={projectId} />;
    const [card] = partsOf([part], "card");
    if (card) return cardAt(card.id);
    const [understood] = partsOf([part], "understood");
    if (understood) return <UnderstoodCard key={`understood:${understood.id}`} projectId={understood.data.project_id} />;
    return null;
  });
  const status = partsOf(parts, "status").at(-1)?.data;
  return (
    <div className="flex flex-col gap-4">
      <ProgressLine items={progress} worklog={partsOf(parts, "worklog").at(-1)?.data} lang={said} live={live} />
      <CoordinationRoom messages={partsOf(parts, "team")} />
      {inOrder}
      {partsOf(parts, "facts").map((facts) => (
        <FactsLine key={facts.id} facts={facts.data} lang={said} />
      ))}
      {partsOf(parts, "notice").map((notice) => (
        <div key={notice.id} role="status" className="flex flex-col gap-2 text-copper">
          <p dir="auto">{pick(notice.data.text, said)}</p>
          <FixAction fix={fixOf(notice.data.fix)} lang={said} />
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
      {status?.state === "failed" && status.step && (
        // a failed Brief keeps its reason and its fix in its reply, after later messages too (audit B7)
        <div role="alert" className="flex flex-col gap-2 text-copper">
          <p dir="auto">{pick(status.step, said)}</p>
          <FixAction fix={fixOf(status.fix)} lang={said} />
        </div>
      )}
    </div>
  );
}

export type ChatLogProps = {
  chat: ChatState;
  /** The log's accessible name: the project chat or the General chat. */
  label: string;
  projectId?: string;
  /** A Deliverable card's Open, with the card it opens from. */
  onOpenDeliverable?: (id: string, card?: HTMLElement) => void;
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

/** Whether ONE is at work in this chat: a message just sent, or the last Brief running (not one waiting for the
 * engineer, a connection or a cap). */
function working({ messages, status, running }: ChatState): boolean {
  if (status === "submitted") return true;
  const last = messages.findLast((message) => message.role === "assistant");
  const state = last && partsOf(last.parts, "status").at(-1)?.data.state;
  if (state) return running && (state === "running" || state === "queued");
  return status === "streaming";
}

/** The messages, as a polite log the engineer can scroll from the keyboard (it is focusable). New content keeps the
 * log at its end while the engineer reads there; scrolled up, a "New below" button shows instead. A card that comes
 * to wait for the engineer is always brought into view. */
export function ChatLog({ chat, label, projectId, onOpenDeliverable, className = "" }: ChatLogProps & { className?: string }) {
  useLanguage();
  const { messages, status, error, failed } = chat;
  const ref = useRef<HTMLDivElement>(null);
  useScrollEdges(ref);
  const atEnd = useRef(true);
  const seen = useRef<Set<string> | null>(null);
  const [below, setBelow] = useState(false);
  const reduced = useReducedMotion();
  const busy = working(chat);
  const lastReply = messages.findLastIndex((message) => message.role === "assistant");
  const sent = useRef<string | undefined>(undefined); // the newest message of the engineer's already in place

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
    // a message the engineer just sent always brings the log to it, even scrolled up: it is where they look now
    const last = messages.at(-1);
    const ownNew = last?.role === "user" && last.id !== sent.current;
    if (atEnd.current || ownNew) toEnd();
    else if (messages.length) setBelow(true);
    if (fresh.length) {
      const card = [...log.querySelectorAll<HTMLElement>("[data-card]")].find((el) => el.dataset.card === fresh[0]);
      card?.scrollIntoView?.({ block: "nearest" });
    }
  }, [messages, status]);

  useLayoutEffect(() => {
    // a message just sent from the box moves from there into its place (after the log has scrolled to it)
    const last = messages.at(-1);
    if (last?.role !== "user" || last.id === sent.current) return;
    sent.current = last.id;
    const from = takeSentFrom();
    const el = [...(ref.current?.querySelectorAll<HTMLElement>("[data-own]") ?? [])].find((li) => li.dataset.own === last.id);
    if (!from || !el) return;
    const to = el.getBoundingClientRect();
    // the side the words start on, from their real rects: the right edges for a line that reads right to left
    const rtl = (baseDirection(textOf(last.parts)) ?? dir()) === "rtl";
    const dx = rtl ? from.right - to.right : from.left - to.left;
    // while it moves it starts outside the log, which would grow the log's scroll area for a moment and flash a
    // scrollbar; the list clips it until it lands
    const list = el.parentElement;
    if (list) list.style.overflow = "clip";
    void play(el, [{ transform: `translate(${dx}px, ${from.top - to.top}px)` }, { transform: "none" }], DUR.base).finally(() => {
      if (list) list.style.overflow = "";
    });
  }, [messages]);

  return (
    // a word too long for its line (a long Arabic word, a file name) breaks only there, never by letter where it
    // fits; a table keeps its words whole and scrolls inside its own box; the chat never scrolls sideways
    <div className={`flex min-h-0 flex-col [overflow-wrap:anywhere] [&_table]:[overflow-wrap:normal] ${className}`}>
      <ContinueBriefs chatId={chat.chatId} onContinued={chat.continued} onLeft={() => void chat.reread()} />
      <div
        ref={ref}
        role="log"
        aria-live="polite"
        aria-atomic="false"
        aria-label={label}
        tabIndex={0}
        data-region-start
        onScroll={(event) => {
          const log = event.currentTarget;
          atEnd.current = log.scrollHeight - log.scrollTop - log.clientHeight <= NEAR_END;
          if (atEnd.current) setBelow(false);
        }}
        className="scroll-fade relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-5 py-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink"
      >
        <ol className="flex flex-col gap-6">
          {messages.length === 0 && <li className="text-slate">{t("empty")}</li>}
          {messages.map((message, index) =>
            message.role === "user" ? (
              <li key={message.id} data-own={message.id} className="max-w-[85%] self-end rounded-2xl bg-stone px-4 py-3">
                {message.metadata?.steering && <p className="text-slate">{t("steering")}</p>}
                {message.metadata?.selection?.length ? (
                  <p className="mb-2 flex w-fit max-w-full rounded-lg bg-paper px-3 py-0.5 text-sm text-slate">
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
                  live={busy && index === lastReply}
                  projectId={projectId}
                  onOpenDeliverable={onOpenDeliverable}
                />
              </li>
            ),
          )}
          {/* once the running Brief sends its work log, Thinking shimmers at its head (ProgressLine) instead */}
          {busy && !(lastReply >= 0 && lastReply === messages.length - 1 && partsOf(messages[lastReply]!.parts, "worklog").length) && (
            <li>
              <span className={reduced ? "text-slate" : "shimmer"}>{t("thinking")}</span>
            </li>
          )}
          {/* a failed Brief's reply says it already, with its fix */}
          {error && !(lastReply >= 0 && failedReply(messages[lastReply]!.parts)) && <ErrorLine error={error} />}
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
