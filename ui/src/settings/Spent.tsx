// Under the spending caps: what is spent today and this month (GET /costs), in USD as the core counts it. Nothing
// shows when the core cannot say.
import { useEffect, useState } from "react";
import { getSpent, type Spent as SpentNow } from "@/api/settingsKept";
import { settings as texts } from "@/texts/settings";
import { useText } from "@/texts/useText";

export function Spent() {
  const t = useText();
  const [spent, setSpent] = useState<SpentNow>();

  useEffect(() => {
    let live = true;
    void getSpent().then(({ data }) => live && data && setSpent(data));
    return () => {
      live = false;
    };
  }, []);

  if (!spent) return null;
  return (
    <section aria-labelledby="spent" className="flex flex-col gap-2 rounded-2xl bg-muted px-5 py-4">
      <h2 id="spent" className="text-lg font-bold">
        {t(texts.spent)}
      </h2>
      <p>{t(texts.spentToday, { amount: spent.today })}</p>
      <p>{t(texts.spentMonth, { amount: spent.month })}</p>
    </section>
  );
}
