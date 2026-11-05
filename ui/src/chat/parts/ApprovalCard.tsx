// A card the engineer must answer: an approval, a Spending Cap pause, a Brief Budget and the like. The core stored it
// before it was shown; the answer goes to POST /cards/{id}. Raising a cap saves the new caps first. A card with a
// payload (Plan 5) is drawn by its kind's renderer in cardKinds (questions: QuestionCard, tables: RowsCard), which sends
// the answers or the ticked rows with the choice.
import { useState } from "react";
import { coreLine, send } from "../../core";
import { fill, pick, t, type Text, texts, useLanguage } from "../../i18n";
import { CapsForm } from "../../settings/AiSettings";
import { type CardAnswer, cardKinds } from "./cardKinds";
import type { CardData } from "./types";

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

function optionLabel(kind: CardData["kind"], option: string): string {
  const key = optionTexts[kind]?.[option] ?? plain[option];
  return key ? t(key) : option;
}

export function ApprovalCard({ id, card }: { id: string; card: CardData }) {
  useLanguage();
  const [chosen, setChosen] = useState<string>();
  const [sending, setSending] = useState(false);
  const [raising, setRaising] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const [sent, setSent] = useState<CardAnswer>({});
  const settled = card.status === "settled" ? (card.choice ?? chosen) : chosen;
  const payload = card.payload;
  const Kind = payload ? cardKinds[card.kind] : undefined;
  // The card as it stands: settled with what was sent as soon as the core took it, before the stream says so.
  const shown: CardData =
    chosen && card.status !== "settled" ? { ...card, status: "settled", choice: chosen, ...sent } : card;

  async function answer(choice: string, extra: CardAnswer = {}) {
    setSending(true);
    setFailed(undefined);
    const response = await send(`/api/cards/${encodeURIComponent(id)}`, "POST", { choice, ...extra });
    setSending(false);
    if (response?.ok) {
      setSent(extra);
      setChosen(choice);
      setRaising(false);
    } else {
      setFailed(await coreLine(response, texts.answerNotSent));
    }
  }

  function choose(option: string) {
    if (option === "raise") return setRaising(!raising);
    void answer(option);
  }

  return (
    <section className="flex flex-col gap-2 rounded-md border border-copper px-3 py-2">
      <h3 className="font-semibold">{pick(card.title)}</h3>
      <p dir="auto">{pick(card.detail)}</p>
      {Kind && (
        <Kind
          card={shown}
          sending={sending}
          onAnswer={(choice, extra) => void answer(choice, extra)}
          label={(option) => optionLabel(card.kind, option)}
        />
      )}
      {card.status === "withdrawn" ? (
        <p className="text-slate">{t("withdrawn")}</p>
      ) : settled ? (
        <p className="text-slate">{fill(t("answered"), { choice: optionLabel(card.kind, settled) })}</p>
      ) : Kind ? null : (
        <>
          <div className="flex flex-wrap gap-2">
            {card.options.map((option) => (
              <button
                key={option}
                type="button"
                disabled={sending}
                aria-expanded={option === "raise" ? raising : undefined}
                onClick={() => choose(option)}
                className={`rounded-md px-3 py-1 disabled:opacity-40 ${option === "no" ? "border border-ink" : "bg-ink text-paper"}`}
              >
                {optionLabel(card.kind, option)}
              </button>
            ))}
          </div>
          {raising && <CapsForm onSaved={() => void answer("raise")} />}
        </>
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}
