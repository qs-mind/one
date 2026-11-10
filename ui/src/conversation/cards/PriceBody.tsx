// A model with no known price, the first time it is used (kind "price"): enter its price per million tokens (saved by
// PUT /settings/ai/prices, then "price" goes on with it), use it without a price (the caps then count its tokens), or
// don't. Asked once per model; the core keeps the answer. No hold: the caps still stop the work.
import { useState } from "react";
import { enterPrice } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { Input } from "@/design/ui/input";
import { cards } from "@/texts/cards";
import { useText } from "@/texts/useText";
import { ConfirmationAction, ConfirmationActions } from "../ai/confirmation";
import type { CardData } from "../parts";

type PriceBodyProps = {
  card: CardData;
  busy: boolean;
  label: (option: string) => string;
  onAnswer: (choice: string) => void;
};

export function PriceBody({ card, busy, label, onAnswer }: PriceBodyProps) {
  const t = useText();
  const [entering, setEntering] = useState(false);
  const [priceIn, setPriceIn] = useState("");
  const [priceOut, setPriceOut] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const model = card.payload?.model;
  const off = busy || saving;

  async function usePrice() {
    if (!model) return;
    setSaving(true);
    setFailed(null);
    const got = await enterPrice({ connector: model.connector, model: model.model }, { in: priceIn.trim(), out: priceOut.trim() });
    setSaving(false);
    if (got.error !== undefined) return setFailed(t(got.error ?? cards.priceNotSaved));
    onAnswer("price"); // the core reads the saved price and goes on with it
  }

  return (
    <div className="flex flex-col gap-4">
      <ConfirmationActions className="mt-1">
        {card.options.map((option, at) => (
          <ConfirmationAction
            key={option}
            variant={at === 0 ? "default" : "outline"}
            disabled={off}
            aria-expanded={option === "price" ? entering : undefined}
            onClick={() => (option === "price" ? setEntering(!entering) : onAnswer(option))}
          >
            {label(option)}
          </ConfirmationAction>
        ))}
      </ConfirmationActions>
      {entering && (
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void usePrice();
          }}
        >
          <Field label={t(cards.priceIn)}>
            <Input dir="ltr" inputMode="decimal" value={priceIn} onChange={(event) => setPriceIn(event.target.value)} />
          </Field>
          <Field label={t(cards.priceOut)} error={failed}>
            <Input dir="ltr" inputMode="decimal" value={priceOut} onChange={(event) => setPriceOut(event.target.value)} />
          </Field>
          <div>
            <ConfirmationAction type="submit" disabled={off || !priceIn.trim() || !priceOut.trim()}>
              {t(cards.useThisPrice)}
            </ConfirmationAction>
          </div>
        </form>
      )}
    </div>
  );
}
