// The action that fixes a core text, where the text shows away from its fix: the chat's error line, a card. The core
// says what happened and what to do; this button takes the engineer there (core.ts Fix). In AI settings and the first
// launch's Connect AI the fix is already in place, so they show none of these.
import type { Fix } from "../core";
import { openSetup } from "../firstlaunch/parts";
import { type Language, t, useLanguage } from "../i18n";

/** The top-bar panels a text elsewhere can open (App listens). */
export type FixPanel = "ai" | "backup";
const listeners = new Set<(panel: FixPanel) => void>();

/** Opens AI settings or Backup from anywhere on the screen, as the More menu does. */
export function openPanel(panel: FixPanel) {
  for (const listener of listeners) listener(panel);
}

export function onOpenPanel(listener: (panel: FixPanel) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const actions: Partial<Record<Fix, { label: "openAiSettings" | "connectAi" | "openBackup"; go: () => void }>> = {
  ai: { label: "openAiSettings", go: () => openPanel("ai") },
  consent: { label: "connectAi", go: () => openSetup("ai", true) },
  backup: { label: "openBackup", go: () => openPanel("backup") },
};

/** The button for `fix`, or nothing ("retry" belongs to the place that ran the check). */
export function FixAction({ fix, lang }: { fix: Fix | undefined; lang?: Language }) {
  useLanguage();
  const action = fix && actions[fix];
  if (!action) return null;
  return (
    <button
      type="button"
      onClick={action.go}
      className="self-start rounded-lg border border-ink px-4 py-1.5 text-ink hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
    >
      {t(action.label, lang)}
    </button>
  );
}
