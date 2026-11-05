// A card the engineer must answer: an approval, a Spending Cap pause, a Brief Budget and the like. The core stored it
// before it was shown; the answer goes to POST /cards/{id}. Raising a cap saves the new caps as they are typed, then
// goes on (its own button, once the last one is saved). A card with a payload (Plan 5) is drawn by its kind's
// renderer in cardKinds (questions: QuestionCard, tables: RowsCard), which sends the answers or the ticked rows with
// the choice. Once answered or withdrawn it is no longer waiting: it drops the copper border and folds to one line
// (its title and the answer), which opens again on a click, so the next card that waits is in sight without
// scrolling.
import { useRef, useState } from "react";
import { coreLine, fixOf, send } from "../../core";
import { FixAction } from "../../shell/FixAction";
import { count, dir, fill, type Language, pick, t, type Text, texts, useLanguage } from "../../i18n";
import { CapsForm } from "../../settings/AiSettings";
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
  // a pause at 80% of a cap; yes and no answer a model of unknown price
  cap: { continue: "capContinue", raise: "capRaise", report: "capReport", yes: "useIt", no: "dontUseIt" },
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

/** `lang`: the Brief's language; the card's words are in it (the page's language by default). */
export function ApprovalCard({ id, card, lang: given }: { id: string; card: CardData; lang?: Language }) {
  const page = useLanguage();
  const lang = given ?? page;
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
      data-approval-card
      data-answered={done || undefined}
      lang={lang}
      dir={dir(lang)}
      className={`flex min-w-0 flex-col rounded-[14px] ${done ? "gap-3 bg-stone/70 px-4 py-2.5" : "gap-3 border border-copper bg-paper px-5 py-4"}`}
    >
      {done ? (
        <h3 className="min-w-0">
          <button
            type="button"
            aria-expanded={unfolded}
            onClick={() => setUnfolded(!unfolded)}
            className="flex w-full min-w-0 items-baseline gap-2 text-start focus-visible:outline-2 focus-visible:outline-ink"
          >
            <span aria-hidden="true" className="shrink-0 text-slate">
              {unfolded ? "▾" : lang === "ar" ? "◂" : "▸"}
            </span>
            <span dir="auto" className="min-w-0 truncate font-semibold">
              {pick(card.title, lang)}
            </span>
            <span className="shrink-0 text-slate">{outcome}</span>
          </button>
        </h3>
      ) : (
        <h3 dir="auto" className="font-semibold">
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
              {card.options.map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={sending}
                  aria-expanded={option === "raise" ? raising : undefined}
                  onClick={() => choose(option)}
                  className={`rounded-lg px-4 py-2 disabled:opacity-40 ${option === "no" ? "border border-ink" : "bg-ink text-paper"}`}
                >
                  {optionLabel(card.kind, option, lang)}
                </button>
              ))}
            </div>
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
