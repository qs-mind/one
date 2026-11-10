// Notices. Callers pass translated strings. Loading is a live line or a progress bar, never a notice.
import { toast } from "sonner";

export const NOTIFY_MS = 6000;

/** A passing notice: gone after 6s. */
export function notify(message: string): string | number {
  return toast(message, { duration: NOTIFY_MS });
}

/** A notice with an undo: it stays until dismissed or replaced, so keyboard and screen-reader users reach it. */
export function notifyUndo(message: string, undoLabel: string, onUndo: () => void): string | number {
  return toast(message, {
    duration: Number.POSITIVE_INFINITY,
    closeButton: true,
    action: { label: undoLabel, onClick: onUndo },
  });
}
