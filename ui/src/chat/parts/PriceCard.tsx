// A model with no known price, the first time it is used (audit B6): its price per million tokens, or use it without a
// price (the caps then count its tokens), or don't. Asked once per model; the core keeps the answer. No press-and-hold:
// it is asked once, and the caps still stop the run.
import { useId, useState } from "react";
import { coreLine, send } from "../../core";
import { pick, t, type Text, texts } from "../../i18n";
import type { CardKindProps } from "./cardKinds";

const field = "rounded-md border border-slate bg-paper px-3 py-2 tabular-nums outline-none focus:border-ink";
const button = "rounded-lg px-4 py-2 disabled:opacity-40";

export function PriceCard({ card, onAnswer, sending, label, lang }: CardKindProps) {
  const [open, setOpen] = useState(false);
  const [priceIn, setPriceIn] = useState("");
  const [priceOut, setPriceOut] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const inId = useId();
  const outId = useId();
  const model = card.payload?.model;
  if (card.status === "settled" || card.status === "withdrawn") return <></>;

  async function usePrice() {
    if (!model) return;
    setSaving(true);
    setFailed(undefined);
    const body = { connector: model.connector, model: model.model, in: priceIn.trim(), out: priceOut.trim() };
    const response = await send("/settings/ai/prices", "PUT", body);
    setSaving(false);
    if (!response?.ok) return setFailed(await coreLine(response, texts.priceNotSaved));
    onAnswer("price"); // the core reads the saved price and goes on with it
  }

  const busy = sending || saving;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {card.options.map((option) =>
          option === "price" ? (
            <button
              key={option}
              type="button"
              aria-expanded={open}
              disabled={busy}
              onClick={() => setOpen(!open)}
              className={`${button} bg-ink text-paper`}
            >
              {label(option)}
            </button>
          ) : (
            <button
              key={option}
              type="button"
              disabled={busy}
              onClick={() => onAnswer(option)}
              className={`${button} border border-ink`}
            >
              {label(option)}
            </button>
          ),
        )}
      </div>
      {open && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void usePrice();
          }}
          className="flex flex-col gap-2"
        >
          <label htmlFor={inId} className="flex flex-col gap-1">
            {t("priceIn", lang)}
          </label>
          <input
            id={inId}
            dir="ltr"
            inputMode="decimal"
            value={priceIn}
            onChange={(event) => setPriceIn(event.target.value)}
            className={field}
          />
          <label htmlFor={outId} className="flex flex-col gap-1">
            {t("priceOut", lang)}
          </label>
          <input
            id={outId}
            dir="ltr"
            inputMode="decimal"
            value={priceOut}
            onChange={(event) => setPriceOut(event.target.value)}
            className={field}
          />
          <div>
            <button type="submit" disabled={busy || !priceIn.trim() || !priceOut.trim()} className={`${button} bg-ink text-paper`}>
              {t("useThisPrice", lang)}
            </button>
          </div>
        </form>
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed, lang)}
        </p>
      )}
    </div>
  );
}
