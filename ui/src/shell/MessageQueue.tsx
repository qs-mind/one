// The message queue while ONE works (kokonut ui's ai-message-queue, as an idea; our own code). While a Brief runs,
// Enter in the message box queues the message instead of interrupting; Ctrl/⌘+Enter still steers the Brief now. The
// queue shows above the box as small chips, «في الطابور: 2», each removable and editable in place (saved as typed).
// When the Brief ends, the next queued message goes by itself, one at a time; after a Stop too, once the core has ended
// the Brief (the engineer removes a chip to keep it from going). A queue that waits (a reload, a Stop the core did not
// take) never clears: «كمّل الطابور» carries on. The first time ever a message is queued, one quiet line under the box
// says how to interrupt.
//
// It is kept in this screen's local storage, per chat, so it survives a reload: a queued message is the engineer's own
// draft, not sent yet, like the words in the box. The core keeps only what was sent (with its Brief), and a queued
// message never starts a Brief, which costs money, while ONE's window is closed.
import { generateId } from "ai";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { SelectionItem } from "../project/types";
import { fill, t, useLanguage } from "../i18n";
import { DUR, play } from "../ui/motion";

export type Queued = { id: string; text: string; selection: SelectionItem[] };
type Stored = { items: Queued[]; paused: boolean };

const EMPTY: Stored = { items: [], paused: false };
const storageKey = (chatId: string) => `qsone.queue.${chatId}`;
const HINT_KEY = "qsone.queue.hint";

function load(chatId: string): Stored {
  try {
    const found = JSON.parse(localStorage.getItem(storageKey(chatId)) ?? "null") as Partial<Stored> | null;
    const items = Array.isArray(found?.items)
      ? found.items.filter((q): q is Queued => typeof q?.id === "string" && typeof q.text === "string" && q.text.trim() !== "")
      : [];
    return { items: items.map((q) => ({ ...q, selection: Array.isArray(q.selection) ? q.selection : [] })), paused: found?.paused === true };
  } catch {
    return EMPTY; // no storage, or something unreadable: an empty queue
  }
}

function save(chatId: string, state: Stored) {
  try {
    if (state.items.length) localStorage.setItem(storageKey(chatId), JSON.stringify(state));
    else localStorage.removeItem(storageKey(chatId));
  } catch {
    // no storage: the queue lasts as long as this page
  }
}

function hintSeen(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) !== null;
  } catch {
    return true; // nowhere to remember it: never shown, rather than shown every time
  }
}

/** The keys that interrupt ONE, as this computer names them. */
export function interruptKeys(): string {
  const platform = typeof navigator === "undefined" ? "" : `${navigator.platform} ${navigator.userAgent}`;
  return /Mac|iPhone|iPad/.test(platform) ? "⌘+Enter" : "Ctrl+Enter";
}

export function useMessageQueue(chatId: string) {
  const [state, setState] = useState<Stored>(() => load(chatId));
  const [hint, setHint] = useState(false);
  const now = useRef(state);
  now.current = state;
  useEffect(() => {
    setState(load(chatId));
    setHint(false);
  }, [chatId]);

  function update(next: (s: Stored) => Stored) {
    const changed = next(now.current);
    now.current = changed;
    save(chatId, changed);
    setState(changed);
  }

  return {
    items: state.items,
    paused: state.paused,
    /** The first message ever queued: the line under the box shows, for as long as the queue does. */
    hint: hint && state.items.length > 0,
    add(text: string, selection: readonly SelectionItem[]) {
      const words = text.trim();
      if (!words) return;
      // a queue started afresh is not paused: a Stop paused the one before it
      update((s) => ({ items: [...s.items, { id: generateId(), text: words, selection: [...selection] }], paused: s.items.length ? s.paused : false }));
      if (!hintSeen()) {
        setHint(true);
        try {
          localStorage.setItem(HINT_KEY, "1");
        } catch {
          // shown this once anyway
        }
      }
    },
    remove(id: string) {
      update((s) => ({ ...s, items: s.items.filter((q) => q.id !== id) }));
    },
    edit(id: string, text: string) {
      update((s) => ({ ...s, items: s.items.map((q) => (q.id === id ? { ...q, text } : q)) }));
    },
    pause() {
      if (now.current.items.length) update((s) => ({ ...s, paused: true }));
    },
    resume() {
      update((s) => ({ ...s, paused: false }));
    },
    /** The next message, taken off the queue; undefined when it is empty or paused. */
    take(): Queued | undefined {
      const [first, ...rest] = now.current.items;
      if (!first || now.current.paused) return undefined;
      update((s) => ({ ...s, items: rest }));
      return first;
    },
    /** A message that did not go goes back to the head of the queue, and the queue waits. */
    putBack(item: Queued) {
      update((s) => ({ items: [item, ...s.items.filter((q) => q.id !== item.id)], paused: true }));
    },
  };
}

export type MessageQueueState = ReturnType<typeof useMessageQueue>;

function Chip({ item, queue }: { item: Queued; queue: MessageQueueState }) {
  const [editing, setEditing] = useState(false);
  const chip = useRef<HTMLLIElement>(null);
  const field = useRef<HTMLInputElement>(null);

  useLayoutEffect(() => {
    // it rises in where it lands; with reduced motion it is just there
    if (chip.current) void play(chip.current, [{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], DUR.base);
  }, []);
  useEffect(() => {
    if (editing) field.current?.focus();
  }, [editing]);

  function done() {
    setEditing(false);
    if (!item.text.trim()) queue.remove(item.id); // emptied: it goes
  }

  return (
    <li ref={chip} className="flex max-w-60 items-center rounded-lg bg-stone text-sm">
      {editing ? (
        <input
          ref={field}
          aria-label={t("queueEditField")}
          dir="auto"
          value={item.text}
          onChange={(event) => queue.edit(item.id, event.target.value)}
          onBlur={done}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === "Escape") {
              event.preventDefault(); // never sends the form the box is in
              event.stopPropagation();
              done();
            }
          }}
          className="min-w-0 rounded-lg bg-paper px-2.5 py-1 outline-none ring-1 ring-ink/20"
        />
      ) : (
        <button
          type="button"
          aria-label={fill(t("queueEdit"), { text: item.text })}
          title={item.text}
          onClick={() => setEditing(true)}
          className="min-w-0 truncate rounded-s-lg py-1 ps-2.5 pe-1 text-start hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
        >
          <bdi dir="auto">{item.text}</bdi>
        </button>
      )}
      <button
        type="button"
        aria-label={fill(t("queueRemove"), { text: item.text })}
        title={fill(t("queueRemove"), { text: item.text })}
        onClick={() => queue.remove(item.id)}
        className="shrink-0 rounded-e-lg px-2 py-1 text-slate hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
      >
        <span aria-hidden="true">✕</span>
      </button>
    </li>
  );
}

/** The queued messages above the message box, and «كمّل الطابور» when the queue waits with nothing running. */
export function MessageQueue({ queue, canResume, onResume }: { queue: MessageQueueState; canResume: boolean; onResume: () => void }) {
  useLanguage();
  if (!queue.items.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-1 pb-2">
      <span aria-live="polite" className="text-sm text-slate">
        {fill(t("queueCount"), { n: queue.items.length })}
      </span>
      <ul aria-label={t("queueLabel")} className="flex min-w-0 flex-wrap items-center gap-1.5">
        {queue.items.map((item) => (
          <Chip key={item.id} item={item} queue={queue} />
        ))}
      </ul>
      {canResume && (
        <button
          type="button"
          onClick={onResume}
          className="rounded-lg border border-ink/15 px-2.5 py-1 text-sm hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
        >
          {t("queueResume")}
        </button>
      )}
    </div>
  );
}

/** The one quiet line under the box, the first time ever a message is queued. */
export function QueueHint({ queue }: { queue: MessageQueueState }) {
  useLanguage();
  if (!queue.hint) return null;
  // one run of Latin keys at the start: the reading order holds in Arabic without isolating it
  return <p className="px-5 pt-1.5 text-xs text-slate">{fill(t("queueHint"), { keys: interruptKeys() })}</p>;
}
