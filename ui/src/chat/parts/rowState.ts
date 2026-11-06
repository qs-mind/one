// The chat and a wide rows document edit one draft and share the answer in flight.
// Memory only; released after the last copy closes. No project text enters browser storage.
import { useCallback, useState, useSyncExternalStore, type Dispatch, type SetStateAction } from "react";

type Entry = { values: Map<string, unknown>; listeners: Set<() => void> };
const entries = new Map<string, Entry>();
function entry(id: string): Entry {
  let value = entries.get(id);
  if (!value) { value = { values: new Map(), listeners: new Set() }; entries.set(id, value); }
  return value;
}

export function useRowState<T>(id: string | undefined, field: string, initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  const [local, setLocal] = useState(initial);
  const shared = id ? entry(id) : undefined;
  if (shared && !shared.values.has(field)) shared.values.set(field, local);
  const subscribe = useCallback((listener: () => void) => {
    if (!id) return () => {};
    const state = entry(id);
    state.listeners.add(listener);
    return () => {
      state.listeners.delete(listener);
      queueMicrotask(() => { if (!state.listeners.size && entries.get(id) === state) entries.delete(id); });
    };
  }, [id]);
  const value = useSyncExternalStore(subscribe, () => shared ? shared.values.get(field) as T : local);
  const set: Dispatch<SetStateAction<T>> = (next) => {
    if (!shared) return setLocal(next);
    shared.values.set(field, typeof next === "function" ? (next as (was: T) => T)(shared.values.get(field) as T) : next);
    for (const listener of shared.listeners) listener();
  };
  return [value, set];
}
