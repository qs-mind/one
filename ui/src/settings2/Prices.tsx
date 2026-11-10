// Prices ONE does not know (the existing PUT /settings/ai/prices): each model the connected providers list without
// a price, with its input and output price in USD per million tokens. Saved when both are in and the engineer leaves
// a box or presses Enter; the core keeps the engineer and the day as the price's source. A model on this computer
// costs nothing and is not asked.
import { useState } from "react";
import { enterPrice, type ModelCard } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { Input } from "@/design/ui/input";
import { textDir } from "@/texts/language";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

const unknown = (card: ModelCard) => !card.on_device && (card.price_in == null || card.price_out == null);

function PriceRow({ card, onSaved }: { card: ModelCard; onSaved: () => void }) {
  const t = useText();
  const [typed, setTyped] = useState({ in: "", out: "" });
  const [state, setState] = useState<"idle" | "saving" | TextPair>("idle");

  async function keep() {
    const price = { in: typed.in.trim(), out: typed.out.trim() };
    if (price.in === "" || price.out === "") return;
    setState("saving");
    const answer = await enterPrice({ connector: card.connector, model: card.model }, price);
    if (!answer.data) return setState(answer.error ?? texts.notSaved);
    setState("idle");
    onSaved(); // the model has its price now, so it leaves this list
  }

  const box = (side: "in" | "out") => (
    <Field label={t(side === "in" ? texts.priceIn : texts.priceOut)} className="flex-[1_1_14rem]">
      <Input
        dir="ltr"
        inputMode="decimal"
        autoComplete="off"
        value={typed[side]}
        onChange={(event) => setTyped((now) => ({ ...now, [side]: event.target.value }))}
        onBlur={() => void keep()}
        onKeyDown={(event) => event.key === "Enter" && void keep()}
      />
    </Field>
  );
  return (
    <li className="flex flex-col gap-3">
      <h4 className="font-bold">
        <bdi dir={textDir(card.name)}>{card.name}</bdi> <span className="font-normal text-muted-foreground">({card.provider})</span>
      </h4>
      <div className="flex flex-wrap gap-4">
        {box("in")}
        {box("out")}
      </div>
      <p aria-live="polite" className={typeof state === "object" ? "text-xs font-bold empty:hidden" : "text-xs text-muted-foreground empty:hidden"}>
        {state === "saving" ? t(texts.saving) : typeof state === "object" ? t(state) : null}
      </p>
    </li>
  );
}

export function Prices({ sheet, onSaved }: { sheet: ModelCard[]; onSaved: () => void }) {
  const t = useText();
  const missing = sheet.filter(unknown);
  if (missing.length === 0) return null;
  return (
    <section aria-labelledby="prices" className="flex flex-col gap-3">
      <h2 id="prices" className="text-lg font-bold">
        {t(texts.prices)}
      </h2>
      <p className="text-xs text-muted-foreground">{t(texts.pricesHelp)}</p>
      <ul className="flex flex-col gap-6">
        {missing.map((card) => (
          <PriceRow key={`${card.connector} ${card.model}`} card={card} onSaved={onSaved} />
        ))}
      </ul>
    </section>
  );
}
