// A one-shot hand-off from the message box to the chat: where the sent words were, so the chat can move the new
// message from there into its place (docs/specs/2026-11-05-motion-design.md, §2.3).
let from: DOMRect | undefined;

/** The box's rect, as the words leave it. */
export function sentFrom(rect: DOMRect): void {
  from = rect;
}

/** The rect handed over, once; undefined when nothing was. */
export function takeSentFrom(): DOMRect | undefined {
  const rect = from;
  from = undefined;
  return rect;
}
