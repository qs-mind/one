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
  agent: ["actionWhatDoing"],
};

export function CommandBar({
  chat,
  onSent,
  floating,
}: {
  chat: ChatState;
  /** After a message went: the shell opens the chat. */
  onSent?: () => void;
  /** Over the canvas, between the zoom controls (start) and the chat (end), in px from each side; without it the
   * bar sits under the General chat's conversation. */
  floating?: { start: number; end: number; bottom: number };
}) {
  useLanguage();
  const selection = useSelection();
  const [draft, setDraft] = useState("");
  const kinds = new Set(selection.map((item) => item.kind));
  const quick = kinds.size === 1 ? actions[selection[0]!.kind] : [];

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
      className={
        floating
          ? "pointer-events-auto w-full max-w-[560px] rounded-[14px] border border-ink/10 bg-paper p-2 shadow-[0_2px_10px_rgb(14_15_18/0.12)]"
          : "mx-auto w-full max-w-[42rem] px-4 pb-4"
      }
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit(draft, true);
        }}
        className="flex flex-col gap-2"
      >
        {selection.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 rounded-md bg-stone px-2 py-0.5">
              <SelectionText items={selection} />
              <button
                type="button"
                aria-label={t("clearSelection")}
                title={t("clearSelection")}
                onClick={() => select([])}
                className="rounded px-1 text-slate hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
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
                className="rounded-md border border-ink/10 px-2 py-0.5 hover:bg-stone disabled:opacity-40"
              >
                {t(key)}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            aria-label={t("message")}
            placeholder={t(selection.length ? "commandBox" : "commandBoxEmpty")}
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
            className="max-h-40 min-h-9 flex-1 resize-none rounded-md border border-ink/10 bg-paper px-3 py-1.5 outline-none focus:border-ink"
          />
          <button
            type="submit"
            disabled={!draft.trim() || !chat.canSend}
            className="rounded-md bg-ink px-4 py-1.5 text-paper disabled:opacity-40"
          >
            {t("send")}
          </button>
          {chat.running && (
            <button type="button" onClick={() => void chat.halt()} className="rounded-md border border-ink px-4 py-1.5">
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
