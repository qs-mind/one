// Plan 6's review board for one Deliverable, beside the canvas at min(60vw, 1100px), or over the whole canvas when
// it is opened full screen. Focus goes to its Close button; Esc (unless something inside closes first) and Close give
// focus back to the element that opened it. The canvas underneath keeps its viewport, so coming back restores it.
// Opened from its card in the chat, it grows from the card's place (a clip-path reveal, 300 ms) and closes back to
// the card while the card is on screen; otherwise it fades. With reduced motion it opens and closes at once.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { DeliverableViewer } from "../deliverables/DeliverableViewer";
import { t, useLanguage } from "../i18n";
import { DUR, play } from "../ui/motion";

const WHOLE = "inset(0px 0px 0px 0px round 0px)";

/** The board clipped to `rect` (both on screen), as a clip-path; never past the board's own edges. */
function clipTo(board: DOMRect, rect: DOMRect): string {
  const px = (n: number) => `${Math.max(0, Math.round(n))}px`;
  const top = px(rect.top - board.top);
  const end = px(board.right - rect.right);
  const bottom = px(board.bottom - rect.bottom);
  const start = px(rect.left - board.left);
  return `inset(${top} ${end} ${bottom} ${start} round 14px)`;
}

/** The card's rect while it is on screen. */
function shownRect(card: HTMLElement | null): DOMRect | undefined {
  if (!card?.isConnected) return undefined;
  const rect = card.getBoundingClientRect();
  const seen = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth;
  return seen ? rect : undefined;
}

/** Which Deliverable is open, whether it fills the canvas, and the element that opened it. */
export function useDeliverablePanel(projectId: string | undefined) {
  const [open, setOpen] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const [origin, setOrigin] = useState<DOMRect>();
  const opener = useRef<HTMLElement | null>(null);
  const card = useRef<HTMLElement | null>(null); // the chat card it grew from
  const board = useRef<HTMLDivElement | null>(null);
  const closing = useRef(false);
  useEffect(() => {
    setOpen(null);
  }, [projectId]);
  return {
    open,
    full,
    /** The card's rect when it opened from one. */
    origin,
    board,
    /** `from`: the chat card it opens from, so it grows from there and closes back to it. */
    show(id: string, fullScreen = false, from?: HTMLElement) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      card.current = from ?? null;
      setOrigin(from?.getBoundingClientRect());
      setFull(fullScreen);
      setOpen(id);
    },
    toggleFull: () => setFull((now) => !now),
    async close() {
      if (closing.current) return;
      closing.current = true;
      const el = board.current;
      if (el) {
        const to = shownRect(card.current);
        const keyframes = to
          ? [{ clipPath: WHOLE, opacity: 1 }, { opacity: 1, offset: 0.4 }, { clipPath: clipTo(el.getBoundingClientRect(), to), opacity: 0 }]
          : [{ opacity: 1 }, { opacity: 0 }];
        await play(el, keyframes, DUR.long);
      }
      closing.current = false;
      setOpen(null);
      const back = opener.current;
      queueMicrotask(() => back?.focus());
    },
  };
}

export type DeliverablePanelState = ReturnType<typeof useDeliverablePanel>;

export function DeliverablePanel({
  panel,
  projectId,
  onSend,
}: {
  panel: DeliverablePanelState;
  projectId: string;
  /** "Fix it" and the like: a message to the Lead QS. */
  onSend(text: string): void;
}) {
  useLanguage();
  const { open, origin, board } = panel;

  useLayoutEffect(() => {
    // it grows from its card, or fades in when opened from elsewhere
    const el = board.current;
    if (!open || !el) return;
    const keyframes = origin
      ? [{ clipPath: clipTo(el.getBoundingClientRect(), origin), opacity: 0 }, { opacity: 1, offset: 0.4 }, { clipPath: WHOLE, opacity: 1 }]
      : [{ opacity: 0 }, { opacity: 1 }];
    void play(el, keyframes, DUR.long);
  }, [open, origin, board]);

  // going full screen takes away the button that did it: focus moves to Close, the one way out, so Esc still works
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (panel.full && !board.current?.contains(document.activeElement)) closeButton.current?.focus();
  }, [panel.full, board]);

  if (!open) return null;
  return (
    <div
      ref={board}
      data-deliverable-panel
      className={`absolute inset-y-0 end-0 z-30 flex flex-col border-ink/10 bg-paper ${
        panel.full ? "start-0" : "w-[min(60vw,1100px)] border-s shadow-[0_2px_10px_rgb(14_15_18/0.12)] max-[899px]:w-full"
      }`}
      onKeyDown={(event) => {
        // Esc closes the open Deliverable, unless it closes something inside it first (an editor, a popover)
        const target = event.target as HTMLElement;
        if (event.key !== "Escape" || event.defaultPrevented) return;
        if (target.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) return;
        void panel.close();
      }}
    >
      <div className="flex justify-end px-3 pt-2">
        {/* focus moves into the panel, so Esc there closes it and gives focus back to the opener */}
        <button ref={closeButton} type="button" autoFocus className="rounded-lg px-3 py-1.5 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink" onClick={() => void panel.close()}>
          {t("close")}
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <DeliverableViewer
          key={open}
          projectId={projectId}
          deliverableId={open}
          mode="full"
          onSend={onSend}
          // full screen has one way out, Close: no second "Leave full screen" stacked under it
          onToggleFullScreen={panel.full ? undefined : panel.toggleFull}
          fullScreen={panel.full}
        />
      </div>
    </div>
  );
}
