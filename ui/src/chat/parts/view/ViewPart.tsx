// A `data-view` part: what the Lead QS chose to show (decision 16.1), drawn only from ONE's blocks. The view takes the
// direction of its own title, so an Arabic view reads right to left on an English page too. A number's chip opens
// its source in the source popover, placed under the chip inside the view's own box.
import { type CSSProperties, useMemo, useRef, useState } from "react";
import type { NumberCell } from "../../../deliverables/types";
import { t, useLanguage } from "../../../i18n";
import { SourcePopover } from "../../../viewers/sheet/SourcePopover";
import { baseDirection } from "../../bidi";
import { BlockBoundary } from "./BlockBoundary";
import { type ViewEnv, ViewEnvContext } from "./env";
import { viewBlocks } from "./registry";
import type { ViewData } from "./types";
import { Words } from "./Words";

type Opened = { cell: NumberCell; style: CSSProperties; from: HTMLElement; focus: boolean };

export function ViewPart({ view, projectId }: { view: ViewData; projectId?: string }) {
  useLanguage();
  const box = useRef<HTMLElement>(null);
  const [opened, setOpened] = useState<Opened | null>(null);
  const direction = baseDirection(view.title) ?? undefined;

  const env = useMemo<ViewEnv>(() => {
    const openSource = (cell: NumberCell, from: HTMLElement, focus: boolean) => {
      const root = box.current?.getBoundingClientRect();
      const at = from.getBoundingClientRect();
      if (!root) return;
      // under the chip, lined up with its start edge (the right edge in an Arabic view)
      const rtl = getComputedStyle(box.current!).direction === "rtl";
      const side = rtl ? { right: Math.max(root.right - at.right, 0) } : { left: Math.max(at.left - root.left, 0) };
      setOpened({ cell, style: { top: at.bottom - root.top, ...side }, from, focus });
    };
    return { sources: view.sources, unsourced: view.unsourced, openSource: projectId ? openSource : undefined };
  }, [view.sources, view.unsourced, projectId]);

  function close() {
    opened?.from.focus();
    setOpened(null);
  }

  return (
    <ViewEnvContext.Provider value={env}>
      <section
        ref={box}
        aria-label={view.title}
        dir={direction}
        className="relative flex flex-col gap-3 rounded-lg border border-stone bg-paper p-4 text-ink"
        // opened by a click, the focus stays on the chip: Escape is heard here too
        onKeyDown={(event) => {
          if (event.key === "Escape" && opened) close();
        }}
      >
        <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h3 dir="auto" className="font-semibold">
            <Words text={view.title} unsourced={view.unsourced} />
          </h3>
          {view.sample && (
            <span className="rounded-full border border-slate px-2.5 text-xs leading-6">{t("sampleData")}</span>
          )}
        </header>
        {view.blocks.map((block, i) => (
          <BlockBoundary key={i} block={block} registry={viewBlocks} />
        ))}
        {view.unsourced.length > 0 && <p className="text-slate">{t("noSourceNote")}</p>}
        {opened && projectId && (
          <SourcePopover
            projectId={projectId}
            cell={opened.cell}
            sources={view.sources}
            style={opened.style}
            focus={opened.focus}
            onClose={close}
          />
        )}
      </section>
    </ViewEnvContext.Provider>
  );
}
