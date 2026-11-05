// Which client BOQs hold sample numbers, as their views said when read: the open document's facts in the top bar
// say «الأرقام عينة» for one (its list entry does not carry it). In memory only, for this run.
import { useSyncExternalStore } from "react";

const samples = new Set<string>();
const listeners = new Set<() => void>();

/** What the client BOQ's view, just read, said about its numbers. */
export function setClientBoqSample(fileId: string, sample: boolean) {
  if (samples.has(fileId) === sample) return;
  if (sample) samples.add(fileId);
  else samples.delete(fileId);
  for (const listener of [...listeners]) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

/** True when the file's client BOQ holds sample numbers; false for none, or anything else. */
export function useClientBoqSample(fileId: string | null): boolean {
  return useSyncExternalStore(subscribe, () => fileId !== null && samples.has(fileId));
}

export function clearClientBoqSamples() {
  samples.clear();
  for (const listener of [...listeners]) listener();
}
