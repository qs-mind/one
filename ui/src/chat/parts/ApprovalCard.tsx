// A card the engineer must answer: an approval, a Spending Cap pause, a Brief Budget and the like. The core stored it
// before it was shown; the answer goes to POST /cards/{id}. Raising a cap saves the new caps first.
import { useState } from "react";
import { coreLine, send } from "../../core";
import { fill, pick, t, type Text, texts, useLanguage } from "../../i18n";
import { CapsForm } from "../../settings/AiSettings";
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
  const settled = card.status === "settled" ? (card.choice ?? chosen) : chosen;

  async function answer(choice: string) {
    setSending(true);
    setFailed(undefined);
    const response = await send(`/api/cards/${encodeURIComponent(id)}`, "POST", { choice });
    setSending(false);
    if (response?.ok) {
      setChosen(choice);
      setRaising(false);
    } else {
      setFailed(await coreLine(response, texts.answerNotSent));
    }
  }

  return (
    <section className="flex flex-col gap-2 rounded-md border border-copper px-3 py-2">
      <h3 className="font-semibold">{pick(card.title)}</h3>
      <p dir="auto">{pick(card.detail)}</p>
      {card.status === "withdrawn" ? (
        <p className="text-slate">{t("withdrawn")}</p>
      ) : settled ? (
        <p className="text-slate">{fill(t("answered"), { choice: optionLabel(card.kind, settled) })}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {card.options.map((option) => (
              <button
                key={option}
                type="button"
                disabled={sending}
                aria-expanded={option === "raise" ? raising : undefined}
                onClick={() => (option === "raise" ? setRaising(!raising) : void answer(option))}
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
