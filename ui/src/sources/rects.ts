// Keeps a few elements' screen boxes fresh while a line or mark is drawn between or round them: a ResizeObserver on
// each, and the window's scroll (any scroll area, in the capture phase) and resize. Changes are read once a frame.
// Nothing runs once `stop` is called, and nothing runs while nothing moves.

const nextFrame = (fn: () => void): (() => void) => {
  if (typeof requestAnimationFrame === "function") {
    const id = requestAnimationFrame(fn);
    return () => cancelAnimationFrame(id);
  }
  const id = setTimeout(fn, 16);
  return () => clearTimeout(id);
};

export function trackRects(els: Element[], onChange: () => void): () => void {
  let pending: (() => void) | null = null;
  const changed = () => {
    pending ??= nextFrame(() => {
      pending = null;
      onChange();
    });
  };
  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(changed) : null;
  for (const el of els) observer?.observe(el);
  addEventListener("scroll", changed, { capture: true, passive: true });
  addEventListener("resize", changed);
  return () => {
    observer?.disconnect();
    removeEventListener("scroll", changed, { capture: true });
    removeEventListener("resize", changed);
    pending?.();
    pending = null;
  };
}
