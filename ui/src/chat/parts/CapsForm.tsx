// The three Spending Caps and the Brief Budget line, in USD (GET and PUT /settings/ai/caps), for a cap card's "Raise
// the cap" (ApprovalCard). Moved here from the old AI settings panel, which the new Settings replaced.
import { useCallback, useEffect, useId, useState } from "react";
import { api } from "../../api";
import { coreLine, send } from "../../core";
import { fill, pick, t, texts, useLanguage } from "../../i18n";
import { Feedback } from "../../ui/Feedback";
import { looksLikeAmount, SaveNote, useSaving } from "../../ui/live";

const field = "rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink";
const primary = "rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40";

/** An amount typed as exact text, never turned into a float on the way; `hint` is a line under it. */
function Amount({
  label,
  value,
  onChange,
  hint,
  invalid = false,
  refused,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  /** The core refused it: its border turns Copper until it saves. */
  invalid?: boolean;
  /** Why the core refused it, said under this field rather than under the whole form. */
  refused?: string;
}) {
  const hintId = useId();
  const refusedId = useId();
  const described = [hint && hintId, refused && refusedId].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1">
        <span>{label}</span>
        <input
          type="text"
          inputMode="decimal"
          dir="ltr"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={described || undefined}
          aria-invalid={invalid || undefined}
          // important: the field's own Slate border, and Ink on focus, would otherwise win
          className={`${field} ${invalid ? "!border-copper" : ""}`}
        />
      </label>
      {hint && (
        <span id={hintId} className="text-slate">
          {hint}
        </span>
      )}
      {refused && (
        <div id={refusedId}>
          <Feedback state="failed">{refused}</Feedback>
        </div>
      )}
    </div>
  );
}

type Amounts = { brief: string; day: string; month: string; budget_above: string };
type Caps = Amounts & { subscription_stops: boolean };
/** GET and PUT /settings/ai/caps: the caps in force and the Recommended Setting, in USD as exact text. */
type CapsAnswer = { caps: Caps; recommended: Caps };
const capFields = [
  ["brief", "capBrief"],
  ["day", "capDay"],
  ["month", "capMonth"],
  ["budget_above", "budgetAbove"],
] as const;

/** The three Spending Caps and the Brief Budget line, in USD, each saved as it is typed: after a pause when it is a
 * whole amount, or on leaving its field. Also used by a cap card's "Raise the cap", whose `go` button goes on once
 * the last change is saved. */
export function CapsForm({ go }: { go?: { label: string; onGo: () => void } }) {
  useLanguage();
  const [caps, setCaps] = useState<Amounts>();
  const [recommended, setRecommended] = useState<Amounts>();
  const { saving, n, later, flush } = useSaving();
  const [bad, setBad] = useState<string>();

  const shown = useCallback((body: CapsAnswer) => {
    const amounts = (from: Caps): Amounts => ({
      brief: from.brief,
      day: from.day,
      month: from.month,
      budget_above: from.budget_above,
    });
    setCaps(amounts(body.caps));
    setRecommended(amounts(body.recommended));
  }, []);

  useEffect(() => {
    let live = true;
    api("/settings/ai/caps")
      .then((response) => (response.ok ? (response.json() as Promise<CapsAnswer>) : undefined))
      .then((body) => live && body?.caps && shown(body))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [shown]);

  function changed(name: keyof Amounts, value: string) {
    if (!caps) return;
    const next = { ...caps, [name]: value };
    setCaps(next);
    // only the amounts on this form: whether the subscription stops is not changed here. What the engineer typed
    // stays as typed: the core's answer never rewrites a field under their hands.
    later(async () => {
      const response = await send("/settings/ai/caps", "PUT", next);
      if (response?.ok) {
        setBad(undefined);
        return null;
      }
      const body = (await response?.clone().json().catch(() => undefined)) as { field?: string } | undefined;
      setBad(body?.field); // the amount the core refused, when it says
      return coreLine(response, texts.capsNotSaved);
    }, Object.values(next).every(looksLikeAmount));
  }

  async function goOn() {
    if (await flush()) go?.onGo();
  }

  // a refusal that names its amount is said under that field, not under the form
  const onField = saving.state === "failed" && capFields.some(([name]) => name === bad);

  return (
    <form onSubmit={(event) => event.preventDefault()} onBlur={() => void flush()} className="flex flex-col gap-2">
      {capFields.map(([name, label]) => (
        <Amount
          key={name}
          label={t(label)}
          value={caps?.[name] ?? ""}
          hint={recommended ? fill(t("recommendedAmount"), { value: recommended[name] }) : undefined}
          onChange={(value) => changed(name, value)}
          invalid={bad === name}
          refused={onField && bad === name && saving.state === "failed" ? pick(saving.line) : undefined}
        />
      ))}
      <SaveNote saving={onField ? { state: "idle" } : saving} n={n} />
      {go && (
        <div>
          <button type="button" disabled={!caps} onClick={() => void goOn()} className={primary}>
            {go.label}
          </button>
        </div>
      )}
    </form>
  );
}
