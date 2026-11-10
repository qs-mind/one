// The questions of a `question` card (3.2): one field each, typed by its `kind` (a date, a number, an amount with its
// unit, or words), or its own options to pick from. "Send" goes once every question has an answer; "no" takes none.
// The core checks what fits (a date that has not passed, 0 to 100 for a percentage) and says so when it does not.
import { useId, useState } from "react";
import type { Schemas } from "@/api/client";
import { Field } from "@/design/Field";
import { ListRow } from "@/design/ListRow";
import { Input } from "@/design/ui/input";
import { RadioGroup, RadioGroupItem } from "@/design/ui/radio-group";
import { textDir } from "@/texts/language";
import { ConfirmationAction, ConfirmationActions } from "./ai/confirmation";

const REFUSE = "no"; // takes nothing (core/qsone/engine/types.py)

type QuestionFieldsProps = {
  questions: readonly Schemas["CardQuestion"][];
  /** The card's options: "sent", and "no" when it may be refused. */
  options: readonly string[];
  label: (option: string) => string;
  disabled: boolean;
  onSend: (choice: string, answers?: Record<string, string>) => void;
};

function Question({ q, value, onChange }: { q: Schemas["CardQuestion"]; value: string; onChange: (v: string) => void }) {
  const id = useId();
  const options = q.options ?? [];
  if (options.length > 0 && !q.free_text)
    return (
      <div className="flex flex-col gap-2">
        <p id={id} dir={textDir(q.text)} className="font-bold">
          {q.text}
        </p>
        <RadioGroup aria-labelledby={id} value={value} onValueChange={(next) => onChange(String(next))} className="gap-2">
          {options.map((option) => (
            <ListRow key={option} frame="boxed" render={<label />} current={value === option} leading={<RadioGroupItem value={option} />} title={option} />
          ))}
        </RadioGroup>
      </div>
    );
  const kind = q.kind ?? "text";
  const typed = kind === "date" ? "date" : "text";
  const field = (
    <Input
      type={typed}
      dir={kind === "text" ? "auto" : "ltr"}
      inputMode={kind === "number" || kind === "money" ? "decimal" : undefined}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
  return (
    <Field label={<span dir={textDir(q.text)}>{q.text}</span>}>
      {q.unit ? (
        <div className="flex items-center gap-2">
          {field}
          <span dir="ltr" className="text-muted-foreground">
            {q.unit}
          </span>
        </div>
      ) : (
        field
      )}
    </Field>
  );
}

export function QuestionFields({ questions, options, label, disabled, onSend }: QuestionFieldsProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const complete = questions.every((q) => (answers[q.id] ?? "").trim() !== "");
  const send = (choice: string) =>
    choice === REFUSE ? onSend(choice) : onSend(choice, Object.fromEntries(questions.map((q) => [q.id, (answers[q.id] ?? "").trim()])));
  return (
    <div className="flex flex-col gap-4">
      {questions.map((q) => (
        <Question key={q.id} q={q} value={answers[q.id] ?? ""} onChange={(v) => setAnswers((all) => ({ ...all, [q.id]: v }))} />
      ))}
      <ConfirmationActions className="mt-1">
        {options.map((option) => (
          <ConfirmationAction
            key={option}
            variant={option === REFUSE ? "outline" : "default"}
            disabled={disabled || (option !== REFUSE && !complete)}
            onClick={() => send(option)}
          >
            {label(option)}
          </ConfirmationAction>
        ))}
      </ConfirmationActions>
    </div>
  );
}
