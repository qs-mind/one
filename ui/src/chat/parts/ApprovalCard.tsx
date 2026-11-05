// A card the engineer must answer: an approval, a Spending Cap pause, a Brief Budget and the like. The core stored it
// before it was shown; the answer goes to POST /cards/{id}. Raising a cap saves the new caps first. A card with a
// payload (Plan 5) also shows its questions or its table, and sends the answers or the ticked rows with the choice.
import { useId, useState } from "react";
import { coreLine, send } from "../../core";
import { fill, pick, t, type Text, texts, useLanguage } from "../../i18n";
import { CapsForm } from "../../settings/AiSettings";
import type { CardData, CardPayload, CardQuestion } from "./types";

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
const REFUSE = "no"; // takes nothing: no answers, no rows (core/qsone/engine/types.py)

function optionLabel(kind: CardData["kind"], option: string): string {
  const key = optionTexts[kind]?.[option] ?? plain[option];
  return key ? t(key) : option;
}

/** Every question has an answer: one of its options, or written text where it takes one. */
function complete(questions: CardQuestion[], answers: Record<string, string>): boolean {
  return questions.every((q) => (answers[q.id] ?? "").trim() !== "");
}

function Questions({
  questions,
  answers,
  onAnswer,
  disabled,
}: {
  questions: CardQuestion[];
  answers: Record<string, string>;
  onAnswer?: (id: string, answer: string) => void;
  disabled: boolean;
}) {
  const group = useId(); // radio groups stay apart when two cards are on the screen
  return (
    <ol className="flex flex-col gap-3">
      {questions.map((q, i) => {
        const options = q.options ?? [];
        const writes = q.free_text || options.length === 0;
        const answer = answers[q.id] ?? "";
        if (!onAnswer) {
          return (
            <li key={q.id} className="flex flex-col">
              <span dir="auto">{q.text}</span>
              <span dir="auto" className="font-semibold">
                {answer}
              </span>
            </li>
          );
        }
        return (
          <li key={q.id}>
            <fieldset className="flex flex-col gap-1" disabled={disabled}>
              <legend dir="auto">{q.text}</legend>
              {options.map((option) => (
                <label key={option} className="flex items-center gap-2" dir="auto">
                  <input
                    type="radio"
                    name={`${group}-${i}`}
                    value={option}
                    checked={answer === option}
                    onChange={() => onAnswer(q.id, option)}
                  />
                  {option}
                </label>
              ))}
              {writes && (
                <input
                  type="text"
                  dir="auto"
                  aria-label={q.text}
                  value={options.includes(answer) ? "" : answer}
                  onChange={(e) => onAnswer(q.id, e.target.value)}
                  className="rounded-md border border-slate px-2 py-1"
                />
              )}
            </fieldset>
          </li>
        );
      })}
    </ol>
  );
}

function Rows({
  payload,
  ticked,
  onTick,
}: {
  payload: CardPayload;
  ticked: number[];
  onTick?: (index: number) => void;
}) {
  const columns = payload.columns ?? [];
  return (
    <table className="text-start">
      <thead>
        <tr>
          {onTick && <th />}
          {columns.map((c) => (
            <th key={c.key} scope="col" className="px-2 text-start font-semibold">
              {pick(c.label)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {(payload.rows ?? []).map((row, i) => (
          <tr key={i} className={!onTick && payload.tick && !ticked.includes(i) ? "text-slate line-through" : undefined}>
            {onTick && (
              <td>
                <input
                  type="checkbox"
                  aria-label={fill(t("tickRow"), { n: i + 1 })}
                  checked={ticked.includes(i)}
                  onChange={() => onTick(i)}
                />
              </td>
            )}
            {columns.map((c) => (
              <td key={c.key} dir="auto" className="px-2">
                {row[c.key] ?? ""}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ApprovalCard({ id, card }: { id: string; card: CardData }) {
  useLanguage();
  const [chosen, setChosen] = useState<string>();
  const [sending, setSending] = useState(false);
  const [raising, setRaising] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [ticked, setTicked] = useState<number[]>([]);
  const settled = card.status === "settled" ? (card.choice ?? chosen) : chosen;
  const payload = card.payload;
  const questions = payload?.questions ?? [];
  const tickable = Boolean(payload?.tick && payload.rows?.length);
  const shownAnswers = card.status === "settled" && card.answers ? card.answers : answers;
  const shownTicked = card.status === "settled" && card.rows_ok ? card.rows_ok : settled === REFUSE ? [] : ticked;

  function ready(option: string): boolean {
    if (option === REFUSE) return true;
    if (!complete(questions, answers)) return false;
    return card.kind !== "rows" || !tickable || ticked.length > 0; // "keep the ticked rows" needs one
  }

  async function answer(choice: string) {
    setSending(true);
    setFailed(undefined);
    const body: { choice: string; answers?: Record<string, string>; rows_ok?: number[] } = { choice };
    if (choice !== REFUSE && questions.length) {
      body.answers = Object.fromEntries(questions.map((q) => [q.id, (answers[q.id] ?? "").trim()]));
    }
    if (choice !== REFUSE && tickable) body.rows_ok = [...ticked].sort((a, b) => a - b);
    const response = await send(`/api/cards/${encodeURIComponent(id)}`, "POST", body);
    setSending(false);
    if (response?.ok) {
      setChosen(choice);
      setRaising(false);
    } else {
      setFailed(await coreLine(response, texts.answerNotSent));
    }
  }

  const open = card.status !== "withdrawn" && !settled;
  const total = payload?.rows?.length ?? 0;

  return (
    <section className="flex flex-col gap-2 rounded-md border border-copper px-3 py-2">
      <h3 className="font-semibold">{pick(card.title)}</h3>
      <p dir="auto">{pick(card.detail)}</p>
      {questions.length > 0 && (settled !== REFUSE || open) && (
        <Questions
          questions={questions}
          answers={shownAnswers}
          disabled={sending}
          onAnswer={open ? (q, a) => setAnswers((all) => ({ ...all, [q]: a })) : undefined}
        />
      )}
      {payload?.rows && payload.rows.length > 0 && (
        <Rows
          payload={payload}
          ticked={shownTicked}
          onTick={
            open && tickable
              ? (i) => setTicked((all) => (all.includes(i) ? all.filter((r) => r !== i) : [...all, i]))
              : undefined
          }
        />
      )}
      {card.status === "withdrawn" ? (
        <p className="text-slate">{t("withdrawn")}</p>
      ) : settled ? (
        <>
          <p className="text-slate">{fill(t("answered"), { choice: optionLabel(card.kind, settled) })}</p>
          {tickable && <p className="text-slate">{fill(t("rowsKept"), { n: shownTicked.length, total })}</p>}
        </>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {card.options.map((option) => (
              <button
                key={option}
                type="button"
                disabled={sending || !ready(option)}
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
