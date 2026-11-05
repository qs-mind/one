// Where a source card stands on the screen (it is in the top layer, ./SourceCard.tsx): under its number, lined up
// with the number's start edge (the right in Arabic); above it when there is more room above; shifted along so it is
// never past the window's edge; and never taller than the room it has, so its last line («افتح المصدر») can always be
// scrolled to.

/** The gap between the number and the card, and the card's least distance from the window's edges. */
export const CARD_GAP = 6;
export const CARD_EDGE = 8;
/** The card's tallest (max-h-96). */
export const CARD_MAX_H = 384;

export type Placed = { top: number; left: number; maxHeight: number };

const clamp = (n: number, low: number, high: number) => Math.min(Math.max(n, low), Math.max(low, high));

export function placeCard(
  anchor: { top: number; bottom: number; left: number; right: number },
  card: { width: number; height: number },
  view: { width: number; height: number },
  rtl: boolean,
): Placed {
  const below = view.height - CARD_EDGE - (anchor.bottom + CARD_GAP);
  const above = anchor.top - CARD_GAP - CARD_EDGE;
  const down = card.height <= below || below >= above;
  // a number near both edges still gets a card it can scroll: at least 120 px, shifted over the number if it must be
  const maxHeight = Math.max(0, Math.min(CARD_MAX_H, view.height - 2 * CARD_EDGE, Math.max(down ? below : above, 120)));
  const height = Math.min(card.height, maxHeight);
  const top = clamp(down ? anchor.bottom + CARD_GAP : anchor.top - CARD_GAP - height, CARD_EDGE, view.height - CARD_EDGE - height);
  const left = clamp(rtl ? anchor.right - card.width : anchor.left, CARD_EDGE, view.width - CARD_EDGE - card.width);
  return { top, left, maxHeight };
}
