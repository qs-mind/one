// The project chat, floating at the inline end of the canvas (left in Arabic, right in English): 340 px, resizable
// from 280 to 560 for this session, from under the top bar to 20 px from the bottom. It shows the conversation; the
// command bar is its composer. It folds to a "Project chat" button. Below 900 px it is a full-height sheet the top
// bar opens. With no AI connected, AI settings take the chat's place (Plan 4).
import { useRef } from "react";
import { ChatLog } from "../chat/Chat";
import { dir, t, useLanguage } from "../i18n";
import { type Ai, AiSettings } from "../settings/AiSettings";
import type { ChatState } from "./useChats";

export const CHAT_WIDTH = { min: 280, max: 560, start: 340, step: 16 };

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
};

/** AI settings while nothing is connected, else the conversation. */
export function ChatBody({ chat, ai, aiMain, onAiClose, label, projectId, onOpenDeliverable }: ChatBodyProps) {
  return (
    <>
      {aiMain && (
        <div className={ai.connected === false ? "min-h-0 flex-1 overflow-y-auto" : "max-h-[50%] shrink-0 overflow-y-auto"}>
          <AiSettings ai={ai} onClose={ai.connected === false ? undefined : onAiClose} />
        </div>
      )}
      {ai.connected !== false && (
        <ChatLog chat={chat} label={label} projectId={projectId} onOpenDeliverable={onOpenDeliverable} className="flex-1" />
      )}
    </>
  );
}

export function ChatPanel({
  open,
  onOpen,
  onClose,
  narrow,
  width,
  onWidth,
  ...body
}: Omit<ChatBodyProps, "label"> & {
  open: boolean;
  onOpen(): void;
  onClose(): void;
  narrow: boolean;
  width: number;
  onWidth(width: number): void;
}) {
  useLanguage();
  const drag = useRef<{ x: number; width: number } | null>(null);
  const rtl = dir() === "rtl";

  if (!open) {
    return narrow ? null : (
      <div data-region="chat" className="absolute end-4 top-2 z-20">
        <button
          type="button"
          data-region-start
          onClick={onOpen}
          className="rounded-[14px] border border-ink/10 bg-paper px-3 py-2 shadow-[0_2px_10px_rgb(14_15_18/0.12)] hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
        >
          {t("projectChat")}
        </button>
      </div>
    );
  }

  // the edge toward the canvas: dragging or pressing the arrow toward the canvas widens the chat
  const widen = rtl ? "ArrowRight" : "ArrowLeft";
  const narrowKey = rtl ? "ArrowLeft" : "ArrowRight";

  return (
    <aside
      aria-label={t("projectChat")}
      data-region="chat"
      tabIndex={-1}
      style={narrow ? undefined : { width }}
      className={
        narrow
          ? "fixed inset-x-0 bottom-0 top-12 z-30 flex flex-col bg-paper pb-28" // room for the command bar over it
          : "absolute bottom-5 end-4 top-2 z-20 flex flex-col rounded-[14px] border border-ink/10 bg-paper shadow-[0_2px_10px_rgb(14_15_18/0.12)]"
      }
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
          className="absolute inset-y-4 start-0 w-1.5 -translate-x-1/2 cursor-col-resize rounded-full hover:bg-ink/10 focus-visible:bg-ink/20 focus-visible:outline-none rtl:translate-x-1/2"
        />
      )}
      <div className="flex items-center justify-between gap-2 border-b border-ink/10 px-4 py-2">
        <h2 className="font-semibold">{t("projectChat")}</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md px-2 py-1 text-slate hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
        >
          {t("closeChat")}
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <ChatBody {...body} label={t("projectChat")} />
      </div>
    </aside>
  );
}
