// A `data-view` part: what the Lead QS chose to show (decision 16.1), drawn only from ONE's blocks. The view takes the
// direction of its own title, so an Arabic view reads right to left on an English page too. A number's chip opens
// its source in the source popover, placed under the chip inside the view's own box.
import { type CSSProperties, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { NumberCell } from "../../../deliverables/types";
import { count, t, useLanguage } from "../../../i18n";
import { scaled } from "../../../ui/scale";
import { SourcePopover } from "../../../viewers/sheet/SourcePopover";
import { openView } from "../../../workspace/views";
import { baseDirection } from "../../bidi";
import { BlockBoundary } from "./BlockBoundary";
import { Section } from "./blocks";
import { type ViewEnv, ViewEnvContext } from "./env";
import { viewBlocks } from "./registry";
import type { ViewBlock, ViewData } from "./types";
import { Words } from "./Words";

const POPOVER_WIDTH = 320; // SourcePopover's w-80, at 100 % (scaled: at the screen's scale)

type Opened = { cell: NumberCell; style: CSSProperties; from: HTMLElement; focus: boolean };

/** The blocks in runs: each run of blocks with the same section together, under that title. */
function sections(blocks: ViewBlock[]): { title: string | null; blocks: ViewBlock[] }[] {
  const runs: { title: string | null; blocks: ViewBlock[] }[] = [];
  for (const block of blocks) {
    const title = block.section || null;
    const last = runs.at(-1);
    if (last && last.title === title) last.blocks.push(block);
    else runs.push({ title, blocks: [block] });
  }
  return runs;
}

/** How many rows the view holds: its tables' rows and its figures. */
const rowsOf = (blocks: ViewBlock[]) =>
  blocks.reduce((n, b) => n + (b.kind === "table" ? b.rows.length : b.kind === "figures" ? b.items.length : 0), 0);

/** A view in the chat; with `id` (its chat part) inside a project, a view wider than the chat shows as a short card
 * that opens it as a document (`whole`: the document draws it at its own width). The chat stays narrow. */
export function ViewPart({ view, projectId, id, whole }: { view: ViewData; projectId?: string; id?: string; whole?: boolean }) {
  useLanguage();
  const box = useRef<HTMLElement>(null);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [wide, setWide] = useState(false);
  const canOpen = !whole && !!id && !!projectId;
  useLayoutEffect(() => {
    const root = box.current;
    if (!canOpen || !root) return;
    // wider than its place: the view itself, or a table inside it that scrolls sideways
    const over = (el: Element) => el.scrollWidth > el.clientWidth + 1;
    if (over(root) || [...root.querySelectorAll("[data-view-scroll]")].some(over)) setWide(true);
  }, [canOpen, view]);
  const direction = baseDirection(view.title) ?? undefined;

  const env = useMemo<ViewEnv>(() => {
    const openSource = (cell: NumberCell, from: HTMLElement, focus: boolean) => {
      const root = box.current?.getBoundingClientRect();
      const at = from.getBoundingClientRect();
      if (!root) return;
      // under the chip, lined up with its start edge (the right edge in an Arabic view), and never past the view's
      // other edge: the popover is 20rem wide at most, and 90% of the view
      const rtl = getComputedStyle(box.current!).direction === "rtl";
      const room = Math.max(root.width - Math.min(scaled(POPOVER_WIDTH), root.width * 0.9), 0);
      const offset = Math.min(Math.max(rtl ? root.right - at.right : at.left - root.left, 0), room);
      const side = rtl ? { right: offset } : { left: offset };
      setOpened({ cell, style: { top: at.bottom - root.top, ...side }, from, focus });
    };
    return { sources: view.sources, unsourced: view.unsourced, openSource: projectId ? openSource : undefined };
  }, [view.sources, view.unsourced, projectId]);

  function close() {
    opened?.from.focus();
    setOpened(null);
  }

  if (wide && canOpen) {
    // the short card: every word wraps, nothing is cut
    return (
      <section aria-label={view.title} dir={direction} className="flex flex-col items-start gap-2 rounded-lg border border-stone bg-paper p-3 text-ink">
        <h3 dir="auto" className="font-semibold break-words">
          <Words text={view.title} unsourced={view.unsourced} />
        </h3>
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate">
          {count("viewRows", rowsOf(view.blocks))}
          {view.sample && <span className="rounded-full border border-slate px-2.5 text-xs leading-6">{t("sampleData")}</span>}
        </p>
        {view.unsourced.length > 0 && <p className="text-sm text-slate">{t("noSourceNote")}</p>}
        <button
          type="button"
          className="rounded-md border border-ink px-3 py-1 text-sm hover:border-copper hover:text-copper focus-visible:outline-2 focus-visible:outline-ink"
          onClick={() => openView(id!, view)}
        >
          {t("openAsDocument")}
        </button>
      </section>
    );
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
        {sections(view.blocks).map((run, i) =>
          run.title ? (
            <Section key={i} title={run.title} blocks={run.blocks} />
          ) : (
            run.blocks.map((block, j) => <BlockBoundary key={`${i}.${j}`} block={block} registry={viewBlocks} />)
          ),
        )}
        {view.unsourced.length > 0 && <p className="text-slate">{t("noSourceNote")}</p>}
        {opened && projectId && (
          <SourcePopover
            projectId={projectId}
            cell={opened.cell}
            sources={view.sources}
            style={opened.style}
            focus={opened.focus}
            from={opened.from}
            onClose={close}
          />
        )}
      </section>
    </ViewEnvContext.Provider>
  );
}
