// A card the engineer must answer: an approval, a Spending Cap pause, a Brief Budget and the like. The core stored it
// before it was shown; the answer goes to POST /cards/{id}. Raising a cap saves the new caps as they are typed, then
// goes on (its own button, once the last one is saved). A card with a payload (Plan 5) is drawn by its kind's
// renderer in cardKinds (questions: QuestionCard, tables: RowsCard), which sends the answers or the ticked rows with
// the choice. Once answered or withdrawn it is no longer waiting: it drops the copper border and folds to a one-line
// trace (the answer, what it was, and when the core took it), which opens again on a click, so the next card that
// waits is in sight without scrolling.
//
// An answer the core marks as costing money or not to be taken back (`hold`, core: stream.HOLD) is a press-and-hold
// (HoldButton), never one click; every other answer, saying no among them, stays one click. ApprovalQueue shows a
// Brief's cards with one open at a time; the rest wait behind it, said as "2 more waiting".
import { useId, useRef, useState } from "react";
import { coreLine, fixOf, send } from "../../core";
import { FixAction } from "../../shell/FixAction";
import { count, dir, fill, type Language, pick, t, type Text, texts, useLanguage } from "../../i18n";
import { CapsForm } from "../../settings/AiSettings";
import { HoldButton } from "../../ui/HoldButton";
import { type CardAnswer, cardKinds } from "./cardKinds";
import type { CardData } from "./types";

/** The event an answered card sends up to the chat. */
export const CARD_ANSWERED = "qsone:card-answered";

type Labels = Record<string, keyof typeof texts>;
const allow: Labels = { yes: "allowOnce", brief: "allowBrief", no: "dontAllow" };

/** The words for each option of each card the core sends: what the answer does, never a bare id. */
const optionTexts: Record<CardData["kind"], Labels> = {
  outside: allow,
  online: allow,
  // a pause at 80% of a cap (yes and no: a card from before the price card)
  cap: { continue: "capContinue", raise: "capRaise", report: "capReport", yes: "useIt", no: "dontUseIt" },
  price: { price: "enterItsPrice", nocap: "useWithoutPrice", no: "dontUseIt" },
  budget: { yes: "startBrief", no: "dontStart" },
  fallback: { yes: "useIt", no: "dontUseIt" },
  desk: { yes: "keepDesk", no: "dontKeep" },
  disagreement: { yes: "keepAsIs", no: "sendBackToFix" }, // the card's own words say "No" sends it back
  question: { sent: "send" },
  keep: { yes: "keepForAll", no: "dontKeep" },
  rows: { keep: "keepTicked", no: "keepNone" },
  cost: { yes: "goAhead", no: "notNow" },
  connector: { yes: "addConnector", no: "dontAdd" },
};
const plain: Labels = { yes: "yes", no: "no" };

function optionLabel(kind: CardData["kind"], option: string, lang?: Language): string {
  const key = optionTexts[kind]?.[option] ?? plain[option];
  return key ? t(key, lang) : option;
}

/** "10:42": when the core took the answer, on the engineer's clock, in the app's numerals. */
function clock(at: string, lang: Language): string {
  const locale = lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(new Date(at));
}

const waiting = (card: CardData) => card.status === "pending" || card.status === undefined;

/** A Brief's cards, one open at a time: the first still waiting; the rest wait behind it and show once it is
 * answered. Each keeps the marks the chat goes by: `data-card`, and `data-waiting` on the open one. */
export function ApprovalQueue({ cards, lang }: { cards: { id: string; data: CardData }[]; lang?: Language }) {
  useLanguage();
  const [answered, setAnswered] = useState<ReadonlySet<string>>(new Set());
  const queue = cards.filter((card) => waiting(card.data) && !answered.has(card.id));
  const open = queue[0]?.id;
  return cards.map((card) => {
    const queued = waiting(card.data) && !answered.has(card.id) && card.id !== open;
    if (queued) return <div key={card.id} data-card={card.id} hidden />;
    return (
      <div key={card.id} data-card={card.id} data-waiting={card.id === open || undefined} className="flex flex-col gap-2">
        <ApprovalCard
          id={card.id}
          card={card.data}
          lang={lang}
          onAnswered={() => setAnswered((was) => new Set(was).add(card.id))}
        />
        {card.id === open && queue.length > 1 && (
          <p lang={lang} className="text-slate">
            {count("moreWaiting", queue.length - 1, {}, lang)}
          </p>
        )}
      </div>
    );
  });
}

/** `lang`: the Brief's language; the card's words are in it (the page's language by default). `onAnswered`: the core
 * took the answer (ApprovalQueue opens the next card). */
export function ApprovalCard({
  id,
  card,
  lang: given,
  onAnswered,
}: {
  id: string;
  card: CardData;
  lang?: Language;
  onAnswered?: () => void;
}) {
  const page = useLanguage();
  const lang = given ?? page;
  const titleId = useId();
  const [chosen, setChosen] = useState<string>();
  const [sending, setSending] = useState(false);
  const [raising, setRaising] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const [sent, setSent] = useState<CardAnswer>({});
  const [unfolded, setUnfolded] = useState(false);
  const box = useRef<HTMLElement>(null);
  const settled = card.status === "settled" ? (card.choice ?? chosen) : chosen;
  const payload = card.payload;
  const Kind = payload ? cardKinds[card.kind] : undefined;
  // The card as it stands: settled with what was sent as soon as the core took it, before the stream says so.
  const shown: CardData =
    chosen && card.status !== "settled" ? { ...card, status: "settled", choice: chosen, ...sent } : card;

  const done = shown.status === "settled" || shown.status === "withdrawn";
  const kept = shown.kind === "rows" && payload?.tick && payload.rows?.length ? (shown.rows_ok ?? []) : undefined;
  const outcome =
    card.status === "withdrawn"
      ? t("withdrawn", lang)
      : kept && settled && settled !== "no"
        ? count("rowsKept", payload!.rows!.length, { kept: kept.length }, lang)
        : settled && fill(t("answered", lang), { choice: optionLabel(card.kind, settled, lang) });

  async function answer(choice: string, extra: CardAnswer = {}) {
    setSending(true);
    setFailed(undefined);
    const response = await send(`/cards/${encodeURIComponent(id)}`, "POST", { choice, ...extra });
    setSending(false);
    if (response?.ok) {
      setSent(extra);
      setChosen(choice);
      setRaising(false);
      onAnswered?.();
      // the chat follows the Brief again: what the Lead QS says next shows (ChatLog)
      box.current?.dispatchEvent(new CustomEvent(CARD_ANSWERED, { bubbles: true }));
    } else {
      setFailed(await coreLine(response, texts.answerNotSent));
    }
  }

  function choose(option: string) {
    if (option === "raise") return setRaising(!raising);
    void answer(option);
  }

  return (
    <section
      ref={box}
      aria-labelledby={titleId}
      data-approval-card
      data-answered={done || undefined}
      lang={lang}
      dir={dir(lang)}
      className={`flex min-w-0 flex-col rounded-[14px] ${done ? "gap-3 bg-stone/70 px-4 py-2.5" : "gap-3 border border-copper bg-paper px-5 py-4"}`}
    >
      {done ? (
        <h3 id={titleId} className="min-w-0">
          <button
            type="button"
            aria-expanded={unfolded}
            onClick={() => setUnfolded(!unfolded)}
            className="flex w-full min-w-0 items-baseline gap-1.5 text-start focus-visible:outline-2 focus-visible:outline-ink"
          >
            <span aria-hidden="true" className="shrink-0 text-slate">
              {unfolded ? "▾" : lang === "ar" ? "◂" : "▸"}
            </span>
            {/* the trace: the answer · what it was · when the core took it */}
            <span className="shrink-0 text-slate">{outcome}</span>
            <span className="shrink-0 text-slate"> · </span>
            <span dir="auto" className="min-w-0 truncate font-semibold">
              {pick(card.title, lang)}
            </span>
            {shown.settled_at && (
              <>
                <span className="shrink-0 text-slate"> · </span>
                <time dateTime={shown.settled_at} className="shrink-0 tabular-nums text-slate">
                  {clock(shown.settled_at, lang)}
                </time>
              </>
            )}
          </button>
        </h3>
      ) : (
        <h3 id={titleId} dir="auto" className="font-semibold">
          {pick(card.title, lang)}
        </h3>
      )}
      <div hidden={done && !unfolded} className="flex min-w-0 flex-col gap-4">
        <p dir="auto">{pick(card.detail, lang)}</p>
        {!done && <FixAction fix={fixOf(card.fix)} lang={lang} />}
        {Kind && (
          <Kind
            card={shown}
            sending={sending}
            onAnswer={(choice, extra) => void answer(choice, extra)}
            label={(option) => optionLabel(card.kind, option, lang)}
            lang={lang}
          />
        )}
        {done || Kind ? null : (
          <>
            <div className="flex flex-wrap gap-2 pt-1">
              {card.options.map((option) => {
                const look = `rounded-lg px-4 py-2 disabled:opacity-40 ${option === "no" ? "border border-ink" : "bg-ink text-paper"}`;
                return card.hold?.options.includes(option) ? (
                  <HoldButton
                    key={option}
                    disabled={sending}
                    onHold={() => choose(option)}
                    hint={t(card.hold.why === "paid" ? "holdHintPaid" : "holdHintIrreversible", lang)}
                    className={look}
                  >
                    {optionLabel(card.kind, option, lang)}
                  </HoldButton>
                ) : (
                  <button
                    key={option}
                    type="button"
                    disabled={sending}
                    aria-expanded={option === "raise" ? raising : undefined}
                    onClick={() => choose(option)}
                    className={look}
                  >
                    {optionLabel(card.kind, option, lang)}
                  </button>
                );
              })}
            </div>
            {card.hold && (
              // seen by eye; screen readers hear it from the held button itself (aria-describedby)
              <p aria-hidden="true" className="text-sm text-slate">
                {t(card.hold.why === "paid" ? "holdHintPaid" : "holdHintIrreversible", lang)}
              </p>
            )}
            {raising && <CapsForm go={{ label: pick(texts.capRaiseGo, lang), onGo: () => void answer("raise") }} />}
          </>
        )}
      </div>
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed, lang)}
        </p>
      )}
    </section>
  );
}
