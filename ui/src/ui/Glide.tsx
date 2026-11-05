// One Stone block behind the row the pointer is on or the keyboard has reached, gliding between rows (150 ms, EASE,
// transform only) instead of each row lighting up on its own. Put it inside the list, which must be `relative
// isolate` (the block sits under the rows). It follows hover, focus and the list's own selection (cmdk's
// data-selected, aria-selected), so the list's arrow keys and roving focus stay as they are. It shows in place the
// first time, glides after; with reduced motion it jumps. The rows must not paint their own hover background.
import { useEffect, useRef } from "react";
import { placeIn, readyNextFrame } from "./indicator";

const ROWS = '[cmdk-item], [role="option"], [role^="menuitem"], button, a[href]';
const SELECTED = '[data-selected="true"], [aria-selected="true"]';

export function Glide({ as: Tag = "span", rows = ROWS }: { as?: "span" | "li" | "div"; rows?: string }) {
  const mark = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = mark.current;
    const box = el?.parentElement;
    if (!el || !box) return;
    let hovered: HTMLElement | null = null;
    let shown: HTMLElement | null = null;
    let cancel = () => {};

    const rowOf = (node: EventTarget | null) => {
      const row = node instanceof Element ? node.closest<HTMLElement>(rows) : null;
      if (!row || row === el || !box.contains(row)) return null;
      return row.matches(':disabled, [aria-disabled="true"], [data-disabled="true"]') ? null : row;
    };
    const focused = () => (box.contains(document.activeElement) ? rowOf(document.activeElement) : null);
    const selected = () => rowOf(box.querySelector(SELECTED));

    const show = (row: HTMLElement | null) => {
      shown = row;
      if (!row) {
        cancel();
        el.removeAttribute("data-on");
        el.removeAttribute("data-ready"); // the next time it shows in place, not sliding in from where it last was
        return;
      }
      const { x, y, w, h } = placeIn(row, box);
      el.style.setProperty("--x", `${x}px`);
      el.style.setProperty("--y", `${y}px`);
      el.style.width = `${w}px`;
      el.style.height = `${h}px`;
      if (el.hasAttribute("data-on")) return;
      el.setAttribute("data-on", "");
      cancel = readyNextFrame(el);
    };

    const over = (event: Event) => {
      const row = rowOf(event.target);
      if (!row) return; // between rows: it stays where it is
      hovered = row;
      show(row);
    };
    const leave = () => {
      hovered = null;
      show(focused() ?? selected());
    };
    const focusIn = (event: Event) => show(rowOf(event.target) ?? shown);
    const focusOut = (event: FocusEvent) => {
      if (!box.contains(event.relatedTarget as Node | null)) show(hovered ?? selected());
    };
    // the list chose another row (arrow keys in cmdk), or its rows changed under it (a search narrowed them)
    const changed = new MutationObserver((records) => {
      const chose = records.some((record) => record.type === "attributes" && (record.target as Element).matches(SELECTED));
      show(chose ? selected() : shown?.isConnected ? shown : (hovered ?? focused() ?? selected()));
    });
    changed.observe(box, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-selected", "aria-selected"] });
    const resized = typeof ResizeObserver === "function" ? new ResizeObserver(() => shown && show(shown)) : undefined;
    resized?.observe(box);

    box.addEventListener("pointerover", over);
    box.addEventListener("pointerleave", leave);
    box.addEventListener("focusin", focusIn);
    box.addEventListener("focusout", focusOut);
    return () => {
      cancel();
      changed.disconnect();
      resized?.disconnect();
      box.removeEventListener("pointerover", over);
      box.removeEventListener("pointerleave", leave);
      box.removeEventListener("focusin", focusIn);
      box.removeEventListener("focusout", focusOut);
    };
  }, [rows]);

  return <Tag ref={mark as never} aria-hidden="true" role={Tag === "li" ? "presentation" : undefined} data-glide className="glide-mark" />;
}
