// A question card (ask_engineer): every question at once, options as radio buttons, a written answer in dir="auto",
// and one Send, open only when every question has an answer. Once sent, or settled in the stream, each answer shows
// under its question. The agent wrote the questions in the engineer's language; ids never show.
import { useId, useState } from "react";
import type { CardKindProps } from "./cardKinds";
import type { CardQuestion } from "./types";

const REFUSE = "no"; // takes nothing: no answers (core/qsone/engine/types.py)

/** Every question has an answer: one of its options, or written text where it takes one. */
function complete(questions: CardQuestion[], answers: Record<string, string>): boolean {
  return questions.every((q) => (answers[q.id] ?? "").trim() !== "");
}

export function QuestionCard({ card, onAnswer, sending, label }: CardKindProps) {
  const group = useId(); // radio groups stay apart when two cards are on the screen
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const questions = card.payload?.questions ?? [];
  const open = card.status !== "settled" && card.status !== "withdrawn";

  if (!open) {
    if (card.choice === REFUSE) return <></>;
    const given = card.answers ?? {};
    return (
      <ol className="flex flex-col gap-4">
        {questions.map((q) => (
          <li key={q.id} className="flex flex-col gap-1">
            <span dir="auto">{q.text}</span>
            <span dir="auto" className="font-semibold">
              {given[q.id] ?? ""}
            </span>
          </li>
        ))}
      </ol>
    );
  }

  const answer = (id: string, value: string) => setAnswers((all) => ({ ...all, [id]: value }));
  function send(choice: string) {
    if (choice === REFUSE) return onAnswer(choice);
    onAnswer(choice, { answers: Object.fromEntries(questions.map((q) => [q.id, (answers[q.id] ?? "").trim()])) });
  }

  return (
    <>
      <ol className="flex flex-col gap-5">
        {questions.map((q, i) => {
          const options = q.options ?? [];
          const given = answers[q.id] ?? "";
          return (
            <li key={q.id}>
              <fieldset className="flex flex-col gap-2" disabled={sending}>
                <legend dir="auto" className="mb-2 font-semibold">{q.text}</legend>
                {options.map((option) => (
                  <label key={option} className="flex items-center gap-3 py-0.5" dir="auto">
                    <input
                      type="radio"
                      name={`${group}-${i}`}
                      value={option}
                      checked={given === option}
                      onChange={() => answer(q.id, option)}
                    />
                    {option}
                  </label>
                ))}
                {(q.free_text || options.length === 0) && (
                  <input
                    type="text"
                    dir="auto"
                    aria-label={q.text}
                    value={options.includes(given) ? "" : given}
                    onChange={(e) => answer(q.id, e.target.value)}
                    className="rounded-lg border border-slate bg-paper px-3 py-2 focus:border-ink focus:outline-1 focus:outline-ink"
                  />
                )}
              </fieldset>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap gap-2 pt-1">
        {card.options.map((option) => (
          <button
            key={option}
            type="button"
            disabled={sending || (option !== REFUSE && !complete(questions, answers))}
            onClick={() => send(option)}
            className={`rounded-lg px-4 py-2 disabled:opacity-40 ${option === REFUSE ? "border border-ink" : "bg-ink text-paper"}`}
          >
            {label(option)}
          </button>
        ))}
      </div>
    </>
  );
}
