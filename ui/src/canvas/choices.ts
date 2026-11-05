// The founder's open choices for the canvas, each one switch, set to the plan's recommended default (Plan 7,
// decision 19). The Arabic names are texts in i18n.ts and the colours are the Tailwind tokens.

/** A Desk frame starts folded to one line, so Desks stay quiet in daily work. */
export const DESKS_START_COLLAPSED = true;

/** "opened": one Project files frame, and a frame for each file the engineer opens, drops or an answer cites.
 * "every": a frame for every file. */
export const FILE_FRAMES: "opened" | "every" = "opened";

/** The project chat starts open beside the canvas (true), or folded to its button (false). */
export const CHAT_STARTS_OPEN = true;

/** A Deliverable card's Open in the chat: "frame" focuses its frame on the canvas (the review board opens beside
 * the canvas only when the Deliverable has no frame yet); "board" always opens the review board beside it. */
export const DELIVERABLE_CARD_OPENS: "frame" | "board" = "frame";
