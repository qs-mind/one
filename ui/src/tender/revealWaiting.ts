// A waiting item brings its place in the thread into view: the last part of its id (contract 3.1, rule 2), or what
// the thread draws for it at its end (rule 4). An item with no place yet shows the thread's newest block (S51).
import type { Schemas } from "@/api/client";

export function revealWaiting(item: Schemas["WaitingItem"]) {
  const thread = document.querySelector('[data-place="tender"] [role="log"]');
  if (!thread) return;
  const places = thread.querySelectorAll(`[data-part="${CSS.escape(item.id)}"]`);
  const place = places[places.length - 1] ?? [...thread.querySelectorAll(".flex-col > *")].at(-1);
  place?.scrollIntoView({ block: "center" });
}
