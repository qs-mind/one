// The words not yet sent in each chat's message box, kept here and not in the box, so they outlive it: the chat folding
// (Full screen, the narrow panel's Esc, a Deliverable opened from a card, the window crossing 1000 px) unmounts the
// box, and switching chats keeps each one's own. Memory only: nothing goes to web storage (decision 4).
import { useCallback, useSyncExternalStore } from "react";

const drafts = new Map<string, string>();
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setDraft(chatId: string, text: string) {
  if (text) drafts.set(chatId, text);
  else drafts.delete(chatId);
  for (const listener of [...listeners]) listener();
}

/** The chat's unsent words and the way to change them. */
export function useDraft(chatId: string): [string, (text: string) => void] {
  const draft = useSyncExternalStore(
    subscribe,
    useCallback(() => drafts.get(chatId) ?? "", [chatId]),
  );
  return [draft, useCallback((text: string) => setDraft(chatId, text), [chatId])];
}

/** For the tests: every draft goes. */
export function clearDrafts() {
  drafts.clear();
  for (const listener of [...listeners]) listener();
}
