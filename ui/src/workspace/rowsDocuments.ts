// A rows approval opened wide is session-only, just like a View from the chat.
import { useSyncExternalStore } from "react";
import type { CardData } from "../chat/parts/types";
import { pick, type Language } from "../i18n";
import { openView } from "./views";

export type RowsDocument = { id: string; card: CardData; lang: Language; onAnswered?: () => void };
const cards = new Map<string, RowsDocument>();
const listeners = new Set<() => void>();
export const rowsDocumentId = (id: string) => `rows:${id}`;
export function updateRowsDocument(value: RowsDocument) {
  const key = rowsDocumentId(value.id);
  if (!cards.has(key)) return;
  cards.set(key, value);
  for (const listener of listeners) listener();
}
export function openRowsDocument(value: RowsDocument) {
  const key = rowsDocumentId(value.id);
  cards.set(key, value);
  openView(key, { title: pick(value.card.title, value.lang), sample: false, blocks: [], sources: {}, unsourced: [] });
}
export function useRowsDocument(id: string): RowsDocument | undefined {
  return useSyncExternalStore((listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; }, () => cards.get(id));
}
