// The one composer: tells the Lead QS what to do with what is selected on the canvas. The selection shows as a
// chip and goes with the message; each quick action only fills a message and sends it. Nothing here calls an agent
// or sends anything outside directly (decision 9).
import { useState } from "react";
import { select, useSelection } from "../canvas/selection";
import type { SelectionItem } from "../canvas/types";
import { SelectionText } from "../chat/Chat";
import { t, type texts, useLanguage } from "../i18n";
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

export function CommandBar({
  chat,
  onSent,
  floating,
  inPanel = false,
}: {
  chat: ChatState;
  /** After a message went: the shell opens the chat. */
  onSent?: () => void;
  /** Over the canvas, between the zoom controls (start) and the chat (end), in px from each side; without it the
   * bar sits under the General chat's conversation. */
  floating?: { start: number; end: number; bottom: number };
  /** At the foot of the open project chat. */
  inPanel?: boolean;
}) {
  useLanguage();
  const selection = useSelection();
  const [draft, setDraft] = useState("");
  const kinds = new Set(selection.map((item) => item.kind));
  const quick = kinds.size === 1 ? actions[selection[0]!.kind] : [];
  const placeholder = t(selection.length ? "commandBox" : "commandBoxEmpty");

  async function submit(text: string, typed: boolean) {
    if (!text.trim() || !chat.canSend) return;
    if (typed) setDraft("");
    const sent = await chat.send(text, selection);
    if (sent) onSent?.();
    else if (typed) setDraft(text);
  }

  const bar = (
    <section
      aria-label={t("commandBar")}
      data-region="command"
      tabIndex={-1}
      data-canvas-cover={floating ? true : undefined}
      className={
        floating
          ? "pointer-events-auto w-full max-w-[560px] rounded-[16px] border border-ink/[0.08] bg-paper p-3 shadow-[0_2px_12px_rgb(14_15_18/0.08)]"
          : inPanel
            ? "shrink-0 px-4 pb-4 pt-3"
            : "mx-auto w-full max-w-[46rem] px-6 pb-6"
      }
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit(draft, true);
        }}
        className="flex flex-col gap-3"
      >
        {selection.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 rounded-lg bg-stone py-1 pe-1 ps-3">
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
                className="rounded-lg border border-ink/15 px-3 py-1 hover:bg-stone disabled:opacity-40"
              >
                {t(key)}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          {/* The box grows with its words, or its placeholder while empty, so neither is ever cut: an invisible copy
              of the text in the same grid cell sets its height (up to max-h-40, then it scrolls). */}
          <div className="grid min-w-0 flex-1">
            <div
              aria-hidden="true"
              dir="auto"
              data-command-mirror
              className="invisible col-start-1 row-start-1 max-h-40 min-h-11 overflow-hidden whitespace-pre-wrap break-words rounded-xl border border-transparent px-4 py-2.5"
            >
              {(draft || placeholder) + " "}
            </div>
          <textarea
            aria-label={t("message")}
            placeholder={placeholder}
            dir="auto"
            rows={1}
            data-region-start
            data-command-box
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void submit(draft, true);
              }
            }}
            className="col-start-1 row-start-1 max-h-40 min-h-11 w-full resize-none overflow-y-auto rounded-xl border border-transparent bg-stone px-4 py-2.5 outline-none placeholder:text-slate focus:border-ink focus:bg-paper"
          />
          </div>
          <button
            type="submit"
            disabled={!draft.trim() || !chat.canSend}
            className="min-h-11 shrink-0 rounded-xl bg-ink px-5 text-paper disabled:opacity-40"
          >
            {t("send")}
          </button>
          {chat.running && (
            <button type="button" onClick={() => void chat.halt()} className="min-h-11 shrink-0 rounded-xl border border-ink px-5">
              {t("stop")}
            </button>
          )}
        </div>
      </form>
    </section>
  );

  return floating ? (
    <div
      className="pointer-events-none absolute z-30 flex justify-center"
      style={{ insetInlineStart: floating.start, insetInlineEnd: floating.end, bottom: floating.bottom }}
    >
      {bar}
    </div>
  ) : (
    bar
  );
}
