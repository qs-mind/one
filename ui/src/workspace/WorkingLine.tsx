// The thin line by the row an agent works on (spec "Agents at work", in place of the canvas cursors): 2 px Slate at
// the row's inline-start edge while an agent thinks or works on the open document. The layer shares the viewer
// root's coordinate space (what `locate` measures from); `box` is the scrolling element whose visible rect bounds
// where a line may show. Moved by `transform` only; placed again on the box's scroll and on resize, in a frame.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { dir, pick, useLanguage } from "../i18n";
import type { AgentInfo, DocKey, ViewerHandle } from "../project/types";

type Line = { y: number; h: number; roles: string[] };

const sameLines = (a: Line[], b: Line[]) =>
  a.length === b.length && a.every((l, i) => l.y === b[i]!.y && l.h === b[i]!.h && l.roles.join() === b[i]!.roles.join());

export function WorkingLine(props: {
  handle: ViewerHandle | null;
  agents: readonly AgentInfo[];
  opened: DocKey;
  box: HTMLElement | null;
}) {
  const { handle, agents, opened, box } = props;
  const lang = useLanguage();
  const layer = useRef<HTMLDivElement>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const busy = agents.filter(
    (a) => (a.state === "thinking" || a.state === "working") && a.focus?.frame === opened && a.focus.anchor,
  );
  const enabled = !!handle && !!box && busy.length > 0;

  const place = () => {
    const root = layer.current?.getBoundingClientRect();
    if (!enabled || !root || !box) return setLines((prev) => (prev.length ? [] : prev));
    const view = box.getBoundingClientRect();
    const found: Line[] = [];
    for (const a of busy) {
      const at = handle.locate(a.focus!.anchor!);
      if (!at || root.top + at.y + at.height <= view.top || root.top + at.y >= view.bottom) continue;
      const role = pick(a.role, lang);
      const line = found.find((l) => l.y === at.y && l.h === at.height);
      if (!line) found.push({ y: at.y, h: at.height, roles: [role] });
      else if (!line.roles.includes(role)) line.roles.push(role);
    }
    setLines((prev) => (sameLines(prev, found) ? prev : found));
  };
  const placeNow = useRef(place);
  placeNow.current = place;

  // Look again when anything it reads changes.
  useLayoutEffect(() => placeNow.current());

  useEffect(() => {
    if (!enabled || !box) return;
    let frame = 0;
    const later = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        placeNow.current();
      });
    };
    box.addEventListener("scroll", later, { passive: true });
    const observer = new ResizeObserver(later);
    observer.observe(box);
    if (layer.current?.parentElement) observer.observe(layer.current.parentElement);
    return () => {
      box.removeEventListener("scroll", later);
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, [enabled, box]);

  if (!enabled) return null;
  const comma = lang === "ar" ? "، " : ", ";
  return (
    <div
      ref={layer}
      data-testid="working-lines"
      dir={dir(lang)}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      {lines.map((l) => (
        <div
          key={`${l.y}:${l.h}`}
          data-working-line=""
          aria-hidden="true"
          title={l.roles.join(comma)}
          className="absolute top-0 w-0.5 bg-slate"
          style={{ insetInlineStart: 0, height: l.h, transform: `translateY(${l.y}px)` }}
        />
      ))}
    </div>
  );
}
