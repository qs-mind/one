// A small either/or choice that saves at once: the options side by side in equal widths, a Stone thumb under the
// chosen one. The thumb is measured from where the option really is (so it lands right in Arabic) and moves by
// transform only (220 ms, EASE). A radio group: one Tab stop, arrow keys move and choose the way the page reads.
import { type KeyboardEvent, useEffect, useLayoutEffect, useRef } from "react";
import { placeIn, readyNextFrame } from "./indicator";

export type SegmentedProps<V extends string> = {
  label: string;
  options: readonly { value: V; label: string }[];
  value: V;
  onChange(value: V): void;
  className?: string;
};

export function Segmented<V extends string>({ label, options, value, onChange, className = "" }: SegmentedProps<V>) {
  const box = useRef<HTMLDivElement>(null);
  const thumb = useRef<HTMLSpanElement>(null);

  const place = () => {
    const el = thumb.current;
    const chosen = box.current?.querySelector<HTMLElement>('[role="radio"][aria-checked="true"]');
    if (!el || !box.current || !chosen) return;
    const { x, y, w, h } = placeIn(chosen, box.current);
    el.style.setProperty("--x", `${x}px`);
    el.style.setProperty("--y", `${y}px`);
    // the options share the width equally, so only the place changes: the size is set, never animated
    el.style.width = `${w}px`;
    el.style.height = `${h}px`;
  };

  useLayoutEffect(place);
  useLayoutEffect(() => (thumb.current ? readyNextFrame(thumb.current) : undefined), []);
  useEffect(() => {
    if (!box.current || typeof ResizeObserver !== "function") return;
    const watch = new ResizeObserver(() => place());
    watch.observe(box.current);
    return () => watch.disconnect();
  }, []);

  function key(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const rtl = event.currentTarget.closest("[dir]")?.getAttribute("dir") === "rtl";
    const step = { ArrowDown: 1, ArrowUp: -1, ArrowRight: rtl ? -1 : 1, ArrowLeft: rtl ? 1 : -1 }[event.key];
    const to = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : step === undefined ? undefined : index + step;
    if (to === undefined) return;
    event.preventDefault();
    const next = options[(to + options.length) % options.length]!;
    box.current?.querySelector<HTMLElement>(`[data-value="${CSS.escape(next.value)}"]`)?.focus();
    if (next.value !== value) onChange(next.value);
  }

  return (
    <div
      ref={box}
      role="radiogroup"
      aria-label={label}
      className={`segmented relative isolate inline-grid auto-cols-fr grid-flow-col rounded-lg bg-paper p-0.5 ring-1 ring-ink/10 ${className}`}
    >
      <span ref={thumb} aria-hidden="true" data-segment-thumb className="segment-thumb" />
      {options.map((option, index) => {
        const chosen = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={chosen}
            tabIndex={chosen ? 0 : -1}
            data-value={option.value}
            onClick={() => !chosen && onChange(option.value)}
            onKeyDown={(event) => key(event, index)}
            className={`whitespace-nowrap rounded-md px-3 py-1 transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-ink ${
              chosen ? "text-ink" : "text-slate hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
