// The action that fixes a core text where the text shows away from its fix (a card): the core says what happened and
// what to do; this link opens the Settings section that does it (core.ts Fix). The web search key is in Settings → AI.
import { paths } from "../../app/paths";
import type { Fix } from "../../core";
import { type Language, t, useLanguage } from "../../i18n";

type Label = "openAiSettings" | "connectAi" | "openBackup" | "setUpSearch";
const actions: Partial<Record<Fix, { label: Label; section: string }>> = {
  ai: { label: "openAiSettings", section: "ai" },
  search: { label: "setUpSearch", section: "ai" },
  consent: { label: "connectAi", section: "ai" },
  backup: { label: "openBackup", section: "backup" },
};

/** The link for `fix`, or nothing ("retry" belongs to the place that ran the check). */
export function FixAction({ fix, lang }: { fix: Fix | undefined; lang?: Language }) {
  useLanguage();
  const action = fix && actions[fix];
  if (!action) return null;
  return (
    <a
      href={`#${paths.settings(action.section)}`}
      className="self-start rounded-lg border border-ink px-4 py-1.5 text-ink hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
    >
      {t(action.label, lang)}
    </a>
  );
}
