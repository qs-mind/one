// The Document viewer: a written Deliverable (a covering letter, a method statement) as the core's view draws it,
// in the Deliverable's own language and direction. Its numbers are references to Project Records and open
// their source on click. An edit is sent as a Suggested change when the engineer leaves the paragraph or presses
// Ctrl+Enter, and shows old → new with ✓ ✗ until he decides; nothing here diffs, computes or saves by itself.
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type CSSProperties, type Ref } from "react";
import { deliverablesApi } from "../../deliverables/api";
import type { Change, DocumentView, NumberCell, Op, Thread } from "../../deliverables/types";
import { count, dir, fill, pick, t, useLanguage, type Text } from "../../i18n";
import { StatusChips } from "../sheet/SheetViewer";
import { SourcePopover } from "../sheet/SourcePopover";
import { opsFor, pendingBlocks, type SlateElement } from "./blockOps";
import { DocEditor, type DocComment, type TextAnchor } from "./plate";

/** A block, or a range of its text (Plan 7's anchor, its document fields: `row` is the block id). */
export type DocumentAnchor = { row?: string; text?: [number, number] };
export type DocumentHandle = {
  /** The block's (or text range's) box in the viewer's own unscaled pixels, or null when it is not there. */
  locate(anchor: DocumentAnchor): DOMRect | null;
};

export type DocumentViewerProps = {
  projectId: string;
  view: DocumentView;
  /** Pending changes and comment threads, as the core lists them. */
  changes?: Change[];
  comments?: Thread[];
  /** "workspace" is "full" without its title shown: the workspace names the open document. */
  mode?: "frame" | "full" | "workspace";
  /** An older version or a Revision: shown, not edited. */
  readOnly?: boolean;
  /** After a change is sent, accepted or rejected: the owner refetches the view and the changes. */
  onChanged?: () => void;
  /** The selected text, as a comment anchor, or null. */
  onSelection?: (anchor: TextAnchor | null) => void;
  onToggleFullScreen?: () => void;
  /** Whether the board is full screen now, for the toggle's words; left out, the full review mode counts as it. */
  fullScreen?: boolean;
  ref?: Ref<DocumentHandle>;
};

const NONE: never[] = [];

/** Open threads as the editor draws them: on their text, or as a mark on their block when moved or on a block. */
function docComments(threads: Thread[]): DocComment[] {
  return threads
    .filter((c) => c.status === "open")
    .flatMap((c): DocComment[] => {
      const a = c.anchor_now ?? c.anchor;
      if (a.type === "text") return [{ id: c.id, block: a.block, start: a.start, end: a.end, kind: c.kind, moved: a.moved }];
      const block = a.type === "row" ? (a.block ?? a.row) : undefined;
      return block ? [{ id: c.id, block, start: 0, end: 0, kind: c.kind, moved: a.moved }] : [];
    });
}

/** A DOM range over [start, end) of a block's text, counted over the text nodes Slate draws for its leaves (references
 * and zero-width fillers have none), so it matches the core's offsets. */
function textRange(block: Element, start: number, end: number): Range | null {
  const range = document.createRange();
  let at = 0;
  let started = false;
  for (const span of block.querySelectorAll("[data-slate-string]")) {
    const node = span.firstChild;
    if (!node || node.nodeType !== Node.TEXT_NODE) continue;
    const length = node.textContent?.length ?? 0;
    if (!started && start <= at + length) {
      range.setStart(node, start - at);
      started = true;
    }
    if (started && end <= at + length) {
      range.setEnd(node, end - at);
      return range;
    }
    at += length;
  }
  return null;
}

export function DocumentViewer(props: DocumentViewerProps) {
  const { projectId, view, changes = NONE, comments = NONE, onChanged } = props;
  const screen = useLanguage();
  const direction = dir(view.language);
  const root = useRef<HTMLDivElement>(null);

  // Changes sent from here show at once; the owner's next list replaces them.
  const [posted, setPosted] = useState<Change[]>([]);
  const [decided, setDecided] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => {
    setPosted([]);
    setDecided(new Set());
  }, [changes, view.version]);
  const allChanges = useMemo(() => {
    const ids = new Set(changes.map((c) => c.id));
    return [...changes, ...posted.filter((c) => !ids.has(c.id))].filter((c) => !decided.has(c.id));
  }, [changes, posted, decided]);
  const pending = useMemo(
    () => pendingBlocks(allChanges, view.blocks, t("docMoveSuggested")),
    [allChanges, view.blocks, screen], // the label follows the screen language
  );
  const marks = useMemo(() => docComments(comments), [comments]);

  const [notice, setNotice] = useState<string | null>(null);
  const say = (line: Text) => setNotice(pick(line));
  const [popover, setPopover] = useState<{ cell: NumberCell; style: CSSProperties; from: HTMLElement; focus: boolean } | null>(
    null,
  );

  /** A box inside the viewer, in its own unscaled pixels (the viewer may sit in a CSS-scaled canvas frame). */
  function boxOf(rect: DOMRect): DOMRect | null {
    const box = root.current;
    if (!box) return null;
    const outer = box.getBoundingClientRect();
    const scale = box.offsetWidth ? outer.width / box.offsetWidth || 1 : 1;
    return new DOMRect((rect.left - outer.left) / scale, (rect.top - outer.top) / scale, rect.width / scale, rect.height / scale);
  }

  useImperativeHandle(props.ref, () => ({
    locate({ row, text }) {
      if (!row) return null;
      const block = [...(root.current?.querySelectorAll("[data-block-id]") ?? [])].find(
        (el) => el.getAttribute("data-block-id") === row,
      );
      if (!block) return null;
      block.scrollIntoView?.({ block: "nearest" });
      const range = text ? textRange(block, text[0], text[1]) : null;
      const rect = range && typeof range.getBoundingClientRect === "function" ? range.getBoundingClientRect() : null;
      return boxOf(rect ?? block.getBoundingClientRect());
    },
  }));

  const onCommit = useCallback(
    async (after: SlateElement[]) => {
      const ops: Op[] = opsFor(view.blocks, after);
      if (ops.length === 0) return true;
      const answer = await deliverablesApi.propose(projectId, view.id, ops);
      if (!answer.ok) {
        say(answer.error);
        return false;
      }
      setNotice(null);
      setPosted((list) => [...list, ...answer.data.changes]);
      onChanged?.();
      return true;
    },
    [projectId, view.id, view.blocks, onChanged],
  );

  const onDecide = useCallback(
    async (changeId: string, accept: boolean) => {
      const answer = accept
        ? await deliverablesApi.accept(projectId, view.id, { ids: [changeId] })
        : await deliverablesApi.reject(projectId, view.id, [changeId]);
      if (!answer.ok) return say(answer.error);
      setDecided((ids) => new Set([...ids, changeId]));
      onChanged?.();
    },
    [projectId, view.id, onChanged],
  );

  const onOpenRef = useCallback(
    (cell: NumberCell, el: HTMLElement, focus: boolean) => {
      const box = boxOf(el.getBoundingClientRect());
      if (!box) return;
      const width = root.current?.offsetWidth ?? 0;
      // Placed under the number, lined up with its start edge (the right edge in RTL).
      const side = direction === "rtl" ? { right: Math.max(width - box.right, 0) } : { left: box.left };
      setPopover({ cell, style: { top: box.bottom, ...side }, from: el, focus });
    },
    [direction],
  );

  function closeSource() {
    popover?.from.focus();
    setPopover(null);
  }

  const onSelection = useRef(props.onSelection);
  onSelection.current = props.onSelection;
  const onSelectText = useCallback((anchor: TextAnchor | null) => onSelection.current?.(anchor), []);

  const untraced = view.untraced;
  const full = props.mode === "full" || props.mode === "workspace";
  return (
    <div
      ref={root}
      className="relative flex h-full min-h-0 flex-col bg-paper text-ink"
      onKeyDown={(event) => {
        if (event.key === "Escape" && popover) closeSource();
      }}
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3">
        {/* in a frame, the frame's strip shows the title: here it is only said, not shown twice */}
        <h2 dir="auto" className={props.mode === "full" ? "text-lg font-semibold" : "sr-only"}>
          {view.title}
        </h2>
        <StatusChips view={view} status={props.mode !== "frame"} />
        <span className="text-slate">{fill(t("reviewVersion"), { n: view.version })}</span>
        {view.revision && <span className="text-slate">{fill(t("reviewRev"), { n: view.revision.no })}</span>}
        {view.pending > 0 && <span>{count("sheetPending", view.pending)}</span>}
        {props.onToggleFullScreen && (
          <button
            type="button"
            aria-pressed={props.fullScreen ?? full}
            className="ms-auto rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
            onClick={props.onToggleFullScreen}
          >
            {(props.fullScreen ?? full) ? t("sheetLeaveFullScreen") : t("sheetFullScreen")}
          </button>
        )}
      </header>
      {view.sample && (
        <p role="note" className="bg-stone px-5 py-2 text-ink">
          {t("sheetSample")}
        </p>
      )}
      {untraced.length > 0 && (
        // the page's words in the page's direction, whatever the letter's: never a full stop thrown to the start
        <p role="note" dir={dir(screen)} lang={screen} className="px-5 py-2 text-slate">
          {count("docUntracedCount", untraced.length)}
        </p>
      )}
      {notice && (
        <p role="alert" className="flex items-start justify-between gap-3 px-5 py-2 text-copper">
          <span>{notice}</span>
          <button type="button" className="rounded px-2 text-ink hover:bg-stone" onClick={() => setNotice(null)}>
            {t("close")}
          </button>
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <DocEditor
          label={view.title}
          blocks={view.blocks}
          refs={view.refs}
          language={view.language}
          readOnly={props.readOnly ?? false}
          pending={pending}
          comments={marks}
          untraced={untraced}
          onCommit={onCommit}
          onDecide={onDecide}
          onOpenRef={onOpenRef}
          sources={view.sources}
          onSelectText={onSelectText}
        />
        {!props.readOnly && (
          <p dir={dir(screen)} lang={screen} className="mx-auto max-w-[44rem] px-8 pb-6 text-xs text-slate">
            {t("docCommitHint")}
          </p>
        )}
      </div>
      {popover && (
        <SourcePopover
          projectId={projectId}
          cell={popover.cell}
          sources={view.sources}
          style={popover.style}
          focus={popover.focus}
          from={popover.from}
          onClose={closeSource}
        />
      )}
    </div>
  );
}
