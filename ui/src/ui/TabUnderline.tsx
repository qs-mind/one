// A 2 px Ink line under the chosen tab, gliding to the next one (220 ms, EASE, transform only: translateX and scaleX
// of a 1 px line). Put it last inside a positioned tablist; it finds the tab with aria-selected="true" there and
// measures it, again whenever the tabs re-render or change size (a language switch, a count in a label).
import { useEffect, useLayoutEffect, useRef } from "react";
import { placeIn, readyNextFrame } from "./indicator";

export function TabUnderline() {
  const line = useRef<HTMLSpanElement>(null);

  const place = () => {
    const el = line.current;
    const box = el?.parentElement;
    if (!el || !box) return;
    const tab = box.querySelector<HTMLElement>(':scope > [role="tab"][aria-selected="true"]');
    if (!tab) return el.setAttribute("data-hidden", "");
    const { x, w } = placeIn(tab, box);
    el.removeAttribute("data-hidden");
    el.style.setProperty("--x", `${x}px`);
    el.style.setProperty("--w", String(w));
  };

  // every render: the parent renders it again when the choice changes
  useLayoutEffect(place);
  useLayoutEffect(() => (line.current ? readyNextFrame(line.current) : undefined), []);
  useEffect(() => {
    const box = line.current?.parentElement;
    if (!box || typeof ResizeObserver !== "function") return;
    const watch = new ResizeObserver(() => place());
    watch.observe(box);
    for (const tab of box.querySelectorAll(':scope > [role="tab"]')) watch.observe(tab);
    return () => watch.disconnect();
  }, []);

  return <span ref={line} aria-hidden="true" data-tab-underline className="tab-underline" />;
}
