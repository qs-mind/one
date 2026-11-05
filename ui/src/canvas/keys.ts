// Shortcuts read KeyboardEvent.code, not key, so they work with the Arabic keyboard layout (decision 10).
// Ctrl on Windows and Linux, Cmd on macOS.
type Keyish = { code: string; ctrlKey: boolean; metaKey: boolean };

export function isMac(): boolean {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
}

export function isMod(event: Keyish): boolean {
  return isMac() ? event.metaKey : event.ctrlKey;
}

export function matches(event: Keyish, code: string): boolean {
  return event.code === code;
}

/** Typing into a box, a text area, an editable block or a grid cell's editor: the key belongs to the content. */
export function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  if (target.closest("textarea, select, [contenteditable=''], [contenteditable='true'], .rdg-editor-container")) return true;
  const input = target.closest("input");
  return input !== null && !["button", "checkbox", "radio", "submit", "reset", "range", "file"].includes(input.type);
}
