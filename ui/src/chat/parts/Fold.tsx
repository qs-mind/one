// The one fold mark of the chat: every folded line (a card's trace, the work log, the Coordination Room, a Review) has
// the same small triangle, pointing down when open and toward the line's end when folded.
import { dir, type Language } from "../../i18n";

export function FoldMark({ open, lang }: { open: boolean; lang?: Language }) {
  return (
    <span aria-hidden="true" data-fold-mark className="inline-block w-3 shrink-0 text-center text-slate">
      {open ? "▾" : dir(lang) === "rtl" ? "◂" : "▸"}
    </span>
  );
}

/** A <summary> with the chat's fold mark in place of the browser's own marker. */
export const summaryLook = "flex cursor-pointer list-none items-baseline gap-1.5 [&::-webkit-details-marker]:hidden";
