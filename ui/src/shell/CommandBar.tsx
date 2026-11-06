// The one composer: tells the Lead QS what to do with what is selected in the document. The selection shows as a
// chip and goes with the message; each quick action only fills a message and sends it. Nothing here calls an agent
// or sends anything outside directly (decision 9).
// At rest it is one quiet pill: the words and one round action. Focused, or with words, a selection, an open model
// card or a Brief at work, it grows into a rounded box with a quiet row under the words: the Lead QS's model and its
// effort for the next Brief, which the message carries. It folds back once it is empty and left (or on Escape).
// Its motion is short and eases out, on transforms, opacity and the row's height only; none with reduced motion.
// While a Brief runs, Enter queues the message (./MessageQueue.tsx) and Ctrl/⌘+Enter steers the Brief now.
import { type FocusEvent, useEffect, useRef, useState } from "react";
import { select, useSelection } from "../project/selection";
import type { SelectionItem } from "../project/types";
import { SelectionText } from "../chat/Chat";
import { sentFrom, takeSentFrom } from "../chat/sent";
import { dir, t, type texts, useLanguage } from "../i18n";
import { ArchivedLine } from "../records/Archived";
import { useProject } from "../records/project";
import { type Ai, keyOf } from "../settings/AiSettings";
import { chip, EffortChip, ModelChip } from "./ComposerChips";
import { useDraft } from "./drafts";
import { MessageQueue, QueueHint, useMessageQueue } from "./MessageQueue";
import type { ChatState } from "./useChats";

const actions: Record<SelectionItem["kind"], (keyof typeof texts)[]> = {
  deliverable: ["actionCheck", "actionSources"],
  file: ["actionAskFile"],
  files: [],
  desk: ["actionSaveDesk"],
  team: [],
  clientboq: [],
  agent: ["actionWhatDoing"],
};

const round = "grid size-9 shrink-0 place-items-center rounded-full transition-[opacity,transform,background-color] duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink active:scale-95";

function Arrow() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 13V3.5M3.75 7.5 8 3.25l4.25 4.25" />
    </svg>
  );
}

function Square() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
      <rect x="2" y="2" width="12" height="12" rx="2.5" fill="currentColor" />
    </svg>
  );
}

export function CommandBar({
  chat,
  ai,
  onSent,
  onConnectAi,
  inPanel = false,
}: {
  chat: ChatState;
  /** The AI settings: the models the engineer's AI links give, the Lead QS's, and the last effort. */
  ai?: Ai;
  /** After a message went: the shell opens the chat. */
  onSent?: () => void;
  /** No model to pick: the AI settings open, to connect one. */
  onConnectAi?: (from: HTMLElement) => void;
  /** At the foot of the open project chat; without it the bar sits under the General chat's conversation. */
  inPanel?: boolean;
}) {
  useLanguage();
  const selection = useSelection();
  const [draft, setDraft] = useDraft(chat.chatId); // kept outside the box: it outlives a folded chat
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false); // Escape folded it while it keeps the focus
  const [picking, setPicking] = useState(false);
  const text = useRef<HTMLTextAreaElement>(null);
  const composer = useRef<HTMLDivElement>(null);
  const kinds = new Set(selection.map((item) => item.kind));
  const quick = kinds.size === 1 ? actions[selection[0]!.kind] : [];
  const placeholder = t(selection.length ? "commandBox" : "commandBoxEmpty");
  const open = (focused && !dismissed) || draft !== "" || chat.running || picking || selection.length > 0;
  // in the chat beside the document it is one line at rest (dense, 5 Nov); under the General chat, roomier
  const lines = inPanel ? "min-h-9 py-1.5 ps-3 leading-6" : "min-h-12 py-2.5 ps-5 leading-7";
  const ends = inPanel ? { open: "pe-3", rest: "pe-10" } : { open: "pe-5", rest: "pe-14" };

  // the Lead QS's model and effort for the next Brief
  const settings = ai?.loaded.state === "ready" ? ai.loaded.settings : undefined;
  const lead = settings?.roles.lead;
  const card = lead && settings?.sheet.find((item) => keyOf(item) === keyOf(lead));
  const levels = card?.efforts ?? [];
  const effort = settings?.effort && levels.includes(settings.effort) ? settings.effort : undefined;
  const shown = effort ?? card?.effort_default ?? "auto";
  const picked = ai?.picked.lead;

  const queue = useMessageQueue(chat.chatId);
  const project = useProject();
  const archived = Boolean(project?.archived_at) && project?.id === chat.chatId; // read-only: nothing to send

  /** The words in the box go on the queue, with the selection they were written for. */
  function enqueue() {
    queue.add(draft, selection);
    setDraft("");
    if (selection.length) select([]); // the selection went with these words: the next ones go without it
  }

  /** The next queued message goes, as if sent now: a new Brief. One that does not go waits at the head. */
  async function sendNext() {
    const item = queue.take();
    if (!item) return;
    const model = picked && settings?.sheet.some((x) => keyOf(x) === keyOf(picked)) ? picked : undefined;
    // the chat as it is now: after a Stop, the one rendered since the Brief ended (never the stopped Brief's, which
    // would steer it)
    if (await latest.current.send(item.text, item.selection, { model, effort })) onSent?.();
    else queue.putBack(item);
  }
  const latest = useRef(chat);
  latest.current = chat;

  // When the Brief ends (and the queue is not paused), the next queued message goes by itself.
  const wasRunning = useRef(chat.running);
  const stopping = useRef(false); // a Stop under way: the next message waits for the core to end the Brief
  useEffect(() => {
    const was = wasRunning.current;
    wasRunning.current = chat.running;
    if (was && !chat.running && !stopping.current) void sendNext();
  }, [chat.running]); // sendNext reads the queue as it is then

  /** Stop ends the Brief; once the core has, the next queued message goes by itself (the engineer removes it to keep
   * it from going). A Stop the core did not take leaves the queue waiting: «كمّل الطابور» carries on. */
  async function stop() {
    stopping.current = true;
    const ended = await chat.halt();
    stopping.current = false;
    if (ended) void sendNext();
    else queue.pause();
  }

  async function submit(words: string, typed: boolean) {
    if (!words.trim() || !chat.canSend) return;
    if (typed) {
      if (text.current) sentFrom(text.current.getBoundingClientRect()); // the chat moves the words on from here
      setDraft("");
    }
    const model = picked && settings?.sheet.some((item) => keyOf(item) === keyOf(picked)) ? picked : undefined;
    const sent = await chat.send(words, selection, { model, effort });
    if (sent && selection.length) select([]); // used: the next message goes without it
    if (sent) onSent?.();
    else if (typed) {
      takeSentFrom(); // the words stay in the box
      setDraft(words);
    }
  }

  function left(event: FocusEvent<HTMLElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false);
  }

  const hasWords = draft.trim() !== "";
  const stopOnly = chat.running && !hasWords;

  const box = (
    <div
      ref={composer}
      data-composer
      data-open={open || undefined}
      onFocus={() => {
        setFocused(true);
        setDismissed(false);
      }}
      onBlur={left}
      onMouseDown={(event) => {
        setDismissed(false); // a press anywhere in it opens it again after Escape
        // a press on the box itself, not on a control in it, writes
        if (event.target !== event.currentTarget && !(event.target as HTMLElement).hasAttribute("data-composer-row")) return;
        event.preventDefault();
        text.current?.focus();
      }}
      className={`relative w-full cursor-text border bg-paper transition-[border-radius,border-color] duration-200 ease-out ${
        inPanel ? "rounded-[10px]" : open ? "rounded-[18px]" : "rounded-[25px]"
      } ${focused ? "border-ink/15" : "border-ink/[0.08]"} shadow-[0_1px_2px_rgb(14_15_18/0.04),0_2px_10px_rgb(14_15_18/0.05)]`}
    >
      {selection.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
          <span className="flex min-w-0 max-w-full items-center gap-1 rounded-lg bg-stone py-1 pe-1 ps-3 text-sm">
            <SelectionText items={selection} />
            <button
              type="button"
              aria-label={t("clearSelection")}
              title={t("clearSelection")}
              onClick={() => select([])}
              className="rounded-md px-2 text-slate hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
            >
              ✕
            </button>
          </span>
          {quick.map((key) => (
            <button
              key={key}
              type="button"
              disabled={!chat.canSend}
              onClick={() => void submit(t(key), false)}
              className="rounded-lg border border-ink/15 px-3 py-1 text-sm hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-40"
            >
              {t(key)}
            </button>
          ))}
        </div>
      )}
      {/* The box grows with its words: an invisible copy of the text in the same grid cell sets its height (up to
          max-h-40, then it scrolls). Empty, it is one line: a placeholder too long for a narrow box ends in "…". */}
      <div className="grid">
        <div
          aria-hidden="true"
          dir={draft ? "auto" : dir()}
          data-command-mirror
          className={`invisible col-start-1 row-start-1 max-h-40 overflow-hidden ${lines} ${draft ? "whitespace-pre-wrap break-words" : "truncate"} ${open ? ends.open : ends.rest}`}
        >
          {(draft || placeholder) + " "}
        </div>
        <textarea
          ref={text}
          aria-label={t("message")}
          placeholder={placeholder}
          dir={draft ? "auto" : dir()}
          rows={1}
          data-region-start
          data-command-box
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            setDismissed(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              // while ONE works, Enter queues; Ctrl/⌘+Enter interrupts: it steers the Brief now
              if (chat.running && !(event.ctrlKey || event.metaKey) && draft.trim()) enqueue();
              else void submit(draft, true);
            } else if (event.key === "Escape" && selection.length > 0) {
              event.preventDefault(); // first Escape: the selection goes; the next folds the box
              select([]);
            } else if (event.key === "Escape" && draft === "" && open) {
              event.preventDefault();
              setDismissed(true);
            } else if (event.key === "Escape" && draft !== "") {
              // words in it: the first Escape only leaves the box, to the chat around it; the draft stays
              event.preventDefault();
              const around = event.currentTarget.closest<HTMLElement>("[data-region='chat']");
              if (around) around.focus();
              else event.currentTarget.blur();
            }
          }}
          className={`col-start-1 row-start-1 max-h-40 w-full resize-none bg-transparent ${lines} outline-none placeholder:text-slate ${draft ? "overflow-y-auto" : "truncate"} ${open ? ends.open : ends.rest}`}
        />
      </div>
      {/* The quiet row: its height opens from nothing, and it fades in; folded, it takes no focus. */}
      <div
        inert={!open}
        className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out ${open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}
      >
        <div className="min-h-0 overflow-hidden">
          <div data-composer-row className="flex items-center gap-0.5 pb-2 pe-24 ps-2.5">
            {settings && !card && settings.sheet.length === 0 && onConnectAi && (
              <button type="button" onClick={(event) => onConnectAi(event.currentTarget)} className={chip}>
                {t("connectAi")}
              </button>
            )}
            {settings && settings.sheet.length > 0 && (
              <ModelChip
                sheet={settings.sheet}
                current={card || undefined}
                onPick={(choice) => ai?.pick({ lead: choice })}
                onOpenChange={setPicking}
                above={composer}
              />
            )}
            {levels.length > 0 && <EffortChip levels={levels} shown={shown} onNext={(next) => ai?.pick({ effort: next })} />}
          </div>
        </div>
      </div>
      <div className={`absolute flex items-center gap-1.5 ${inPanel ? "bottom-[0.3125rem] end-[0.3125rem] [&>button]:size-7" : "bottom-1.5 end-1.5"}`}>
        {chat.running && hasWords && (
          <button type="button" aria-label={t("stop")} title={t("stop")} onClick={() => void stop()} className={`${round} bg-stone text-ink hover:bg-ink/10`}>
            <Square />
          </button>
        )}
        {stopOnly ? (
          <button type="button" aria-label={t("stop")} title={t("stop")} onClick={() => void stop()} className={`${round} bg-ink text-paper`}>
            <Square />
          </button>
        ) : (
          <button
            type="submit"
            aria-label={chat.running ? t("queueAdd") : t("send")}
            title={chat.running ? t("queueAdd") : t("send")}
            disabled={!hasWords || !chat.canSend}
            className={`${round} bg-ink text-paper disabled:cursor-default disabled:opacity-20 disabled:active:scale-100`}
          >
            <Arrow />
          </button>
        )}
      </div>
    </div>
  );

  const bar = (
    <section
      aria-label={t("commandBar")}
      data-region="command"
      tabIndex={-1}
      className={inPanel ? "shrink-0 pt-2" : "mx-auto w-full max-w-[46rem] px-6 pb-6"}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (chat.running) enqueue();
          else void submit(draft, true);
        }}
      >
        {archived ? (
          <ArchivedLine projectId={chat.chatId} />
        ) : (
          <>
            <MessageQueue queue={queue} canResume={!chat.running} onResume={() => {
              queue.resume();
              void sendNext();
            }} />
            {box}
            <QueueHint queue={queue} />
          </>
        )}
      </form>
    </section>
  );

  return bar;
}
