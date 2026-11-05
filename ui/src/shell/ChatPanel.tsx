// The project chat, floating at the inline end of the canvas (left in Arabic, right in English): 420 px, so its cards
// and tables have room, resizable from 320 to 640 for this session, from under the top bar to 20 px from the bottom. It shows the conversation, and
// the command bar, its composer, sits at its foot: one message box (it floats over the canvas only while the chat is
// folded). It folds to a "Project chat" button. Below 900 px it is a full-height sheet the top bar opens. With no AI
// connected, AI settings take the chat's place (Plan 4). The open chat marks itself as covering the canvas
// (data-canvas-cover), so the canvas shows its frames beside it, never under it.
import { type ReactNode, useRef } from "react";
import { ChatLog } from "../chat/Chat";
import { ConsentNeeded } from "../firstlaunch/ConnectAi";
import { dir, t, useLanguage } from "../i18n";
import { type Ai, AiSettings } from "../settings/AiSettings";
import { useScrollEdges } from "../ui/useScrollEdges";
import type { ChatState } from "./useChats";

export const CHAT_WIDTH = { min: 320, max: 640, start: 420, step: 16 };

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

/** AI settings while nothing is connected, else the conversation; above both, the way to the AI consent while the
 * engineer has not given it (until then the core refuses every AI call). */
export function ChatBody({ chat, ai, aiMain, onAiClose, label, projectId, onOpenDeliverable }: ChatBodyProps) {
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
  composer,
  ...body
}: Omit<ChatBodyProps, "label"> & {
  open: boolean;
  onOpen(): void;
  onClose(): void;
  narrow: boolean;
  width: number;
  onWidth(width: number): void;
  /** The command bar, at the chat's foot. */
  composer?: ReactNode;
}) {
  useLanguage();
  const drag = useRef<{ x: number; width: number } | null>(null);
  const rtl = dir() === "rtl";

  if (!open) {
    return narrow ? null : (
      <div data-region="chat" data-canvas-cover className="absolute end-4 top-3 z-20">
        <button
          type="button"
          data-region-start
          onClick={onOpen}
          className="rounded-[14px] border border-ink/[0.08] bg-paper px-4 py-2.5 shadow-[0_2px_12px_rgb(14_15_18/0.08)] hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
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
      data-canvas-cover
      tabIndex={-1}
      style={narrow ? undefined : { width }}
      className={
        narrow
          ? "fixed inset-x-0 bottom-0 top-14 z-30 flex flex-col bg-paper"
          : "absolute bottom-4 end-4 top-3 z-20 flex flex-col rounded-[16px] border border-ink/[0.08] bg-paper shadow-[0_2px_12px_rgb(14_15_18/0.08)]"
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
      <div className="flex items-center justify-between gap-3 px-5 pb-1 pt-3">
        <h2 className="font-semibold">{t("projectChat")}</h2>
        <button
          type="button"
          onClick={onClose}
          className="-me-2 rounded-lg px-3 py-1.5 text-slate hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
        >
          {t("closeChat")}
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <ChatBody {...body} label={t("projectChat")} />
      </div>
      {composer}
    </aside>
  );
}
