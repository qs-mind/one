// Focus rings for the keyboard only. Every ring in ONE is `focus-visible:`, but an engine may still match
// :focus-visible after a click (WebKitGTK, the Linux app's engine, left a black box on the work log line after one).
// So a press with the mouse, pen or a touch marks <html> with data-pointer, and styles.css hides the ring while it is
// there; a key that moves focus (Tab, the arrows, Home, End, Page Up/Down, F6) clears it, and the rings are back.
const MOVES = /^(Tab|Arrow(Up|Down|Left|Right)|Home|End|PageUp|PageDown|F6)$/;

/** Starts marking how focus was last moved; returns a function that stops it. */
export function installPointerFocus(root: HTMLElement = document.documentElement): () => void {
  const pointer = () => root.setAttribute("data-pointer", "");
  const key = (event: KeyboardEvent) => {
    if (MOVES.test(event.key)) root.removeAttribute("data-pointer");
  };
  document.addEventListener("pointerdown", pointer, true);
  document.addEventListener("keydown", key, true);
  return () => {
    document.removeEventListener("pointerdown", pointer, true);
    document.removeEventListener("keydown", key, true);
    root.removeAttribute("data-pointer");
  };
}
