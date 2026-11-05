// Plan 6's review board for one Deliverable, beside the canvas at min(60vw, 1100px), or over the whole canvas when
// it is opened full screen. Focus goes to its Close button; Esc (unless something inside closes first) and Close give
// focus back to the element that opened it. The canvas underneath keeps its viewport, so coming back restores it.
import { useEffect, useRef, useState } from "react";
import { DeliverableViewer } from "../deliverables/DeliverableViewer";
import { t, useLanguage } from "../i18n";

/** Which Deliverable is open, whether it fills the canvas, and the element that opened it. */
export function useDeliverablePanel(projectId: string | undefined) {
  const [open, setOpen] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    setOpen(null);
  }, [projectId]);
  return {
    open,
    full,
    show(id: string, fullScreen = false) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setFull(fullScreen);
      setOpen(id);
    },
    toggleFull: () => setFull((now) => !now),
    close() {
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
  if (!panel.open) return null;
  return (
    <div
      className={`absolute inset-y-0 end-0 z-30 flex flex-col border-ink/10 bg-paper ${
        panel.full ? "start-0" : "w-[min(60vw,1100px)] border-s shadow-[0_2px_10px_rgb(14_15_18/0.12)] max-[899px]:w-full"
      }`}
      onKeyDown={(event) => {
        // Esc closes the open Deliverable, unless it closes something inside it first (an editor, a popover)
        const target = event.target as HTMLElement;
        if (event.key !== "Escape" || event.defaultPrevented) return;
        if (target.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) return;
        panel.close();
      }}
    >
      <div className="flex justify-end px-3 pt-2">
        {/* focus moves into the panel, so Esc there closes it and gives focus back to the opener */}
        <button type="button" autoFocus className="rounded-lg px-3 py-1.5 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink" onClick={panel.close}>
          {t("close")}
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <DeliverableViewer
          key={panel.open}
          projectId={projectId}
          deliverableId={panel.open}
          mode="full"
          onSend={onSend}
          onToggleFullScreen={panel.toggleFull}
        />
      </div>
    </div>
  );
}
