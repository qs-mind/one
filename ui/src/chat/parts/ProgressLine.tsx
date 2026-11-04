// The Progress Line: one line per agent at work, its name and what it is doing now. Each line is updated in place.
import { pick, t, useLanguage } from "../../i18n";
import type { ProgressData } from "./types";

export function ProgressLine({ items }: { items: { id: string; data: ProgressData }[] }) {
  useLanguage();
  if (items.length === 0) return null;
  return (
    <ul aria-label={t("progressLine")} aria-live="polite" className="flex flex-col gap-0.5 text-slate">
      {items.map(({ id, data }) => (
        <li key={id}>
          <span className="font-semibold text-ink">{pick(data.agent)}</span>{" "}
          <span dir="auto">{pick(data.text)}</span>
        </li>
      ))}
    </ul>
  );
}
