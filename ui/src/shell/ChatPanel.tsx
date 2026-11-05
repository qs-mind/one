// The project chat: a column at the inline end of the screen (left in Arabic, right in English), beside the document
// on the Stone ground, 320 px to start, resizable from 280 to 480 for this session, 12 px inside (dense, 5 Nov). Its
// head names the role it talks to and who is working now (that opens the team list); then the conversation, and the
// command bar at its foot, the only message box. It folds to a 12 px edge that keeps the waiting dot. Below 1000 px it is a panel over the
// document, opened from the top bar's chat button and closed with Esc; below 640 px the panel covers the window's
// width. With no AI connected, AI settings take the chat's place (Plan 4).
import { type ReactNode, useEffect, useRef } from "react";
import { ChatLog } from "../chat/Chat";
import { ConsentNeeded } from "../firstlaunch/ConnectAi";
import { dir, t, useLanguage } from "../i18n";
import { TeamNow } from "../project/live/TeamNow";
import { type Ai, AiSettings } from "../settings/AiSettings";
import { useScrollEdges } from "../ui/useScrollEdges";
import { Notices } from "./Notices";
import type { ChatState } from "./useChats";

export const CHAT_WIDTH = { min: 280, max: 480, start: 320, step: 16 };

const clamp = (width: number) => Math.min(CHAT_WIDTH.max, Math.max(CHAT_WIDTH.min, Math.round(width)));

export type ChatBodyProps = {
  chat: ChatState;
  ai: Ai;
  /** AI settings in place of the chat: nothing connected yet, or the first one just connected. */
  aiMain: boolean;
  onAiClose(): void;
  label: string;
  projectId?: string;
  onOpenDeliverable?: (id: string) => void;
  /** The project chat beside the document: 12 px round and between messages. */
  dense?: boolean;
};

/** AI settings while nothing is connected, else the conversation; above both, the way to the AI consent while the
 * engineer has not given it (until then the core refuses every AI call); under them, the import reports and the
 * backup question (Notices). */
export function ChatBody({ chat, ai, aiMain, onAiClose, label, projectId, onOpenDeliverable, dense }: ChatBodyProps) {
  const settings = useRef<HTMLDivElement>(null);
  useScrollEdges(settings);
  return (
    <>
      <ConsentNeeded />
      {aiMain && (
        <div ref={settings} className={`scroll-fade ${ai.connected === false ? "min-h-0 flex-1 overflow-y-auto" : "max-h-[50%] shrink-0 overflow-y-auto"}`}>
          <AiSettings ai={ai} onClose={ai.connected === false ? undefined : onAiClose} />
        </div>
      )}
      {ai.connected !== false && (
        <ChatLog chat={chat} label={label} projectId={projectId} onOpenDeliverable={onOpenDeliverable} className="flex-1" dense={dense} />
      )}
      <Notices />
    </>
  );
}

/** The copper dot of "waiting": on the folded edge and on the narrow window's chat button. */
export function WaitingDot() {
  return <span data-waiting-dot aria-hidden="true" className="size-[7px] shrink-0 rounded-full bg-copper" />;
}

export function ChatPanel({
  open,
  onOpen,
  onClose,
  narrow,
  small,
  width,
  onWidth,
  waiting,
  composer,
  ...body
}: Omit<ChatBodyProps, "label"> & {
  open: boolean;
  onOpen(): void;
  onClose(): void;
  narrow: boolean;
  /** Below 640 px: the panel covers the window's width. */
  small: boolean;
  width: number;
  onWidth(width: number): void;
  /** Something waits for the engineer: the folded edge keeps the dot. */
  waiting: boolean;
  /** The command bar, at the chat's foot. */
  composer?: ReactNode;
}) {
  useLanguage();
  const drag = useRef<{ x: number; width: number } | null>(null);
  const panel = useRef<HTMLElement>(null);
  const rtl = dir() === "rtl";

  // the narrow panel takes the focus as it opens, so Esc closes it from the start
  useEffect(() => {
    if (open && narrow) panel.current?.focus();
  }, [open, narrow]);

  if (!open) {
    return narrow ? null : (
      <div data-region="chat" className="flex shrink-0 -ms-4">
        <button
          type="button"
          data-region-start
          data-chat-edge
          aria-label={t("openChat")}
          title={t("openChat")}
          onClick={onOpen}
          className="flex w-3 flex-col items-center rounded-full pt-5 hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-ink"
        >
          {waiting && <WaitingDot />}
        </button>
      </div>
    );
  }

  // the edge toward the document: dragging or pressing the arrow toward it widens the chat
  const widen = rtl ? "ArrowRight" : "ArrowLeft";
  const narrowKey = rtl ? "ArrowLeft" : "ArrowRight";

  function close() {
    if (narrow) document.querySelector<HTMLElement>("[data-chat-button]")?.focus(); // back to what opened it
    onClose();
  }

  return (
    <aside
      ref={panel}
      aria-label={t("projectChat")}
      data-region="chat"
      tabIndex={-1}
      style={narrow ? (small ? undefined : { width: CHAT_WIDTH.start }) : { width }}
      onKeyDown={(event) => {
        // Esc closes the narrow panel; not one a popover from it (in a portal) or the message box used first
        if (!narrow || event.key !== "Escape" || event.defaultPrevented || !event.currentTarget.contains(event.target as Node)) return;
        event.preventDefault();
        close();
      }}
      className={`flex min-h-0 flex-col gap-1 outline-none [&_[data-own]]:bg-paper [&_[data-own]_p.bg-paper]:bg-stone ${
        narrow
          ? `fixed bottom-0 end-0 top-11 z-30 bg-stone shadow-[0_0_0_1px_rgb(110_106_100/0.18),0_10px_28px_rgb(14_15_18/0.07)] ${small ? "start-0" : "max-w-full"}`
          : "relative shrink-0"
      }`}
    >
      {!narrow && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t("chatWidth")}
          aria-valuemin={CHAT_WIDTH.min}
          aria-valuemax={CHAT_WIDTH.max}
          aria-valuenow={width}
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === widen) onWidth(clamp(width + CHAT_WIDTH.step));
            else if (event.key === narrowKey) onWidth(clamp(width - CHAT_WIDTH.step));
            else return;
            event.preventDefault();
          }}
          onPointerDown={(event) => {
            drag.current = { x: event.clientX, width };
            event.currentTarget.setPointerCapture?.(event.pointerId);
          }}
          onPointerMove={(event) => {
            const from = drag.current;
            if (!from) return;
            const moved = rtl ? event.clientX - from.x : from.x - event.clientX;
            onWidth(clamp(from.width + moved));
          }}
          onPointerUp={() => (drag.current = null)}
          // in the 12 px gap beside the document
          className="absolute inset-y-4 -start-[9px] z-10 w-1.5 cursor-col-resize rounded-full hover:bg-ink/10 focus-visible:bg-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        />
      )}
      <div className={`flex items-start justify-between gap-3 px-3 ${narrow ? "pt-3" : "pt-1"}`}>
        <div className="flex min-w-0 flex-col">
          <h2 className="text-sm font-semibold">{t("roleLead")}</h2>
          <TeamNow />
        </div>
        <button
          type="button"
          onClick={close}
          className="-me-2 shrink-0 rounded-lg px-2 py-1 text-xs text-slate hover:bg-paper hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
        >
          {t("closeChat")}
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <ChatBody {...body} label={t("projectChat")} dense />
      </div>
      <div className={narrow ? "px-3 pb-3" : "px-3"}>{composer}</div>
    </aside>
  );
}
