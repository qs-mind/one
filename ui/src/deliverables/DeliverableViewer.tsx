// One Deliverable, as the viewer registry gives it to the workspace and the chat's side panel. It loads its own data
// and loads it again when the project's live stream says the Deliverable changed. In `mode="full"` it is the review board: the viewer, then
// Changes, Comments, Versions and Close-out, with the exports; `mode="workspace"` is the same board as the open
// document of the workspace, which names the document itself. Everything it draws stays inside its own box.
import { useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { Anchor, LocateOptions, ViewerProps } from "../project/types";
import { fill, language, pick, t, useLanguage } from "../i18n";
import { ChangesPanel } from "../review/ChangesPanel";
import { CommentsPanel } from "../review/CommentsPanel";
import { ExportMenu } from "../review/ExportMenu";
import { FillPreview } from "../review/FillPreview";
import { rangePlace } from "../review/place";
import { SignOff } from "../review/SignOff";
import { VersionsPanel } from "../review/VersionsPanel";
import { TabUnderline } from "../ui/TabUnderline";
import { DocumentViewer, type DocumentHandle } from "../viewers/document/DocumentViewer";
import type { TextAnchor } from "../viewers/document/plate";
import { UndoNotice, type UndoHandle } from "../ui/UndoNotice";
import { isMod, isTyping } from "../project/keys";
import { SheetViewer, type SheetHandle, type SheetRange } from "../viewers/sheet/SheetViewer";
import { deliverablesApi, type Accepted, type Rejected } from "./api";
import type { CommentAnchor, FillPlanInfo, View } from "./types";
import { useDeliverable, type Subscribe } from "./useDeliverable";

export type DeliverableViewerProps = ViewerProps & {
  /** Sends a message to the Lead QS, as the chat does ("Fix it"). */
  onSend?: (text: string) => void;
  /** The Fill Plan of the client's own file; left out, the board finds the newest one itself. */
  fillPlanId?: string | null;
  onToggleFullScreen?: () => void;
  /** Whether the board is full screen now, for the toggle's words; left out, the full review mode counts as it. */
  fullScreen?: boolean;
  /** The project's live stream; Plan 7's live store can stand in for the shared one. */
  subscribe?: Subscribe;
};

type Tab = "changes" | "comments" | "versions" | "closeout";
type Selected = { comment: CommentAnchor; anchor: Anchor; label: string };

const quote = (text: string) => (text.length > 40 ? `${text.slice(0, 40).trimEnd()}…` : text);

/** The engineer's selection in a sheet, as a comment anchor, a canvas anchor and a label («البنود 03/01–03/04»). */
function fromRange(view: View, range: SheetRange): Selected {
  const { from, to } = range;
  const single = from.row === to.row && from.column === to.column;
  return {
    comment: single ? { type: "cell", row: from.row, column: from.column } : { type: "range", from, to },
    anchor: { row: from.row, column: from.column },
    label: rangePlace(view, from.row, to.row, single ? from.column : undefined),
  };
}

function fromText(text: TextAnchor): Selected {
  return {
    comment: text,
    anchor: { row: text.block, text: [text.start, text.end] },
    label: fill(t("placeQuote"), { quote: quote(text.quote) }),
  };
}

/** A tab's count: a small chip after the label, a space before it (read as "Comments 1"). */
function CountChip({ n }: { n: number }) {
  return (
    <>
      {" "}
      <bdi dir="ltr" data-count className="ms-1 inline-block min-w-5 rounded-full bg-ink/[0.08] px-1.5 text-center text-xs leading-5 tabular-nums">
        {n}
      </bdi>
    </>
  );
}

export function DeliverableViewer(props: DeliverableViewerProps) {
  const { projectId, deliverableId, mode } = props;
  useLanguage();
  const state = useDeliverable(projectId, deliverableId, props.subscribe);
  const { view, reload } = state;
  const root = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const sheet = useRef<SheetHandle>(null);
  const doc = useRef<DocumentHandle>(null);
  const [tab, setTab] = useState<Tab>("changes");
  const [selected, setSelected] = useState<Selected | null>(null);
  const [fillOpen, setFillOpen] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState<FillPlanInfo | null>(null);
  // The last accept's or reject's Undo, «اتقبل · تراجع», while its window lasts (Ctrl+Z too); and the change the
  // review is on
  const [undo, setUndo] = useState<{ token: string; windowMs: number; takeFocus: boolean; label: string } | null>(null);
  const undoNotice = useRef<UndoHandle>(null);
  const [current, setCurrent] = useState<string | null>(null);

  // The board finds the Sheet's newest Fill Plan, and looks again each time the Deliverable is loaded (a plan the
  // Lead QS saves is announced on the live stream).
  const findPlan = view?.kind === "sheet" && props.fillPlanId === undefined;
  useEffect(() => {
    if (!findPlan) return;
    let live = true;
    void deliverablesApi.fillPlans(projectId, deliverableId).then((answer) => {
      if (live && answer.ok) setPlan(answer.data.plans[0] ?? null);
    });
    return () => {
      live = false;
    };
  }, [projectId, deliverableId, findPlan, view]);

  /** Where the anchor is, relative to this viewer's root, in its own unscaled pixels (it may sit in a scaled box). */
  function locate(anchor: Anchor, options?: LocateOptions): DOMRect | null {
    const inner = (view?.kind === "sheet" ? sheet.current : doc.current)?.locate(anchor, options) ?? null;
    const outer = root.current;
    const wrapper = body.current;
    if (!inner || !outer || !wrapper) return inner;
    const a = outer.getBoundingClientRect();
    const b = wrapper.getBoundingClientRect();
    const scale = outer.offsetWidth ? a.width / outer.offsetWidth || 1 : 1;
    return new DOMRect(inner.x + (b.left - a.left) / scale, inner.y + (b.top - a.top) / scale, inner.width, inner.height);
  }
  useImperativeHandle(props.ref, () => ({ locate }));

  // Reported when the selection changes, not when the owner re-renders with a new callback.
  const onSelection = useRef(props.onSelection);
  onSelection.current = props.onSelection;
  const viewRef = useRef(view);
  viewRef.current = view;
  const report = useCallback((found: Selected | null) => {
    setSelected(found);
    onSelection.current?.(found?.anchor ?? null, found?.label ?? null);
  }, []);
  const onSheetSelection = useCallback(
    (range: SheetRange | null) => report(range && viewRef.current ? fromRange(viewRef.current, range) : null),
    [report],
  );
  const onTextSelection = useCallback((text: TextAnchor | null) => report(text ? fromText(text) : null), [report]);

  const announce = useCallback((line: string) => {
    setStatus(""); // the same line twice is said twice
    queueMicrotask(() => setStatus(line));
  }, []);
  const changed = useCallback(() => void reload(), [reload]);
  const accepted = useCallback((answer: Accepted, how: { keys: boolean } = { keys: false }) => {
    if (answer.undo && answer.window_ms)
      setUndo({ token: answer.undo, windowMs: answer.window_ms, takeFocus: !how.keys, label: t("reviewAcceptedShort") });
  }, []);
  const rejected = useCallback((answer: Rejected, how: { keys: boolean } = { keys: false }) => {
    if (answer.undo && answer.window_ms)
      setUndo({ token: answer.undo, windowMs: answer.window_ms, takeFocus: !how.keys, label: t("reviewRejectedShort") });
  }, []);
  const onCurrent = useCallback((change: { id: string } | null) => setCurrent(change?.id ?? null), []);

  if (!view) {
    return (
      <div ref={root} className={`h-full w-full bg-paper text-slate ${mode === "workspace" ? "p-3" : "flex items-center justify-center p-4"}`}>
        {state.error ? (
          <p role="alert" className="text-copper">
            {pick(state.error)}
          </p>
        ) : (
          <p>{t("deliverableLoading")}</p>
        )}
      </div>
    );
  }

  const viewer =
    view.kind === "sheet" ? (
      <SheetViewer
        ref={sheet}
        projectId={projectId}
        view={view}
        changes={state.changes}
        comments={state.comments}
        mode={mode}
        onChanged={changed}
        onSelection={onSheetSelection}
        onToggleFullScreen={props.onToggleFullScreen}
        fullScreen={props.fullScreen}
        review={{ active: tab === "changes" && !fillOpen && view.pending > 0, current }}
        onAccepted={accepted}
        onRejected={rejected}
      />
    ) : (
      <DocumentViewer
        ref={doc}
        projectId={projectId}
        view={view}
        changes={state.changes}
        comments={state.comments}
        mode={mode}
        onChanged={changed}
        onSelection={onTextSelection}
        onToggleFullScreen={props.onToggleFullScreen}
        fullScreen={props.fullScreen}
      />
    );

  const tabs: [Tab, string][] = [
    ["changes", t("reviewChanges")],
    ["comments", t("reviewComments")],
    ["versions", t("reviewVersions")],
    ["closeout", t("reviewCloseOut")],
  ];
  const tabId = (key: Tab) => `review-${view.id}-${key}`;
  // As the open document, a review with nothing in it is only its tab row: the sheet takes the height. Another tab,
  // a Fill preview or a change to review opens the panel again.
  const folded =
    mode === "workspace" &&
    tab === "changes" &&
    !fillOpen &&
    !state.changes.some((c) => c.status === "pending") &&
    state.stale.length === 0;
  const onLocate = (anchor: Anchor) => void locate(anchor);
  const undoLine = undo && (
    <UndoNotice
      key={undo.token}
      ref={undoNotice}
      label={undo.label}
      token={undo.token}
      windowMs={undo.windowMs}
      takeFocus={undo.takeFocus}
      onUndone={() => {
        setUndo(null);
        announce(t("undoDone"));
        changed();
      }}
      onEnd={() => setUndo(null)}
    />
  );

  return (
    <div
      ref={root}
      className="relative flex h-full w-full min-h-0 flex-col bg-paper text-ink"
      onKeyDown={(event) => {
        // Ctrl+Z (by the key's place, so the Arabic layout works too) takes back the last accept or reject
        if (!undo || !isMod(event) || event.code !== "KeyZ" || event.shiftKey || isTyping(event.target)) return;
        event.preventDefault();
                undoNotice.current?.undo();
      }}
    >
      {/* full: a Sheet is as tall as its rows, up to 60% (75% as the open document: the room is the data's), and the
          review panels take the rest; a Document keeps 3/5 */}
      <div
        ref={body}
        className={
          folded
            ? "flex min-h-0 flex-1 flex-col"
            : view.kind === "sheet"
              ? `flex min-h-0 ${mode === "workspace" ? "max-h-[75%]" : "max-h-[60%]"} flex-[0_1_auto] flex-col`
              : "min-h-0 flex-[3_1_0%]"
        }
      >
        {viewer}
      </div>
      <div data-review-panel={folded ? "folded" : "open"} className={`flex min-h-0 flex-col bg-stone/50 ${folded ? "shrink-0" : "flex-[2_1_0%]"}`}>
        <div className={`flex flex-wrap items-center gap-3 ${mode === "workspace" ? "px-3 py-1" : "px-5 pb-1 pt-3"}`}>
          <div role="tablist" aria-label={t("reviewPanels")} className="relative flex flex-wrap gap-1">
            {tabs.map(([key, label]) => (
              <button
                key={key}
                id={`${tabId(key)}-tab`}
                type="button"
                role="tab"
                aria-selected={tab === key}
                aria-controls={tabId(key)}
                className={`rounded-t-lg px-3 py-1.5 transition-colors duration-150 ${tab === key ? "text-ink" : "text-slate hover:text-ink"}`}
                onClick={() => {
                  setTab(key);
                  setFillOpen(null);
                }}
              >
                {label}
                {key === "changes" && view.pending > 0 && <CountChip n={view.pending} />}
                {key === "comments" && view.open_comments > 0 && <CountChip n={view.open_comments} />}
              </button>
            ))}
            <TabUnderline />
          </div>
          {undoLine}
          <div className="ms-auto">
            <ExportMenu
              projectId={projectId}
              view={view}
              fillPlanId={props.fillPlanId !== undefined ? props.fillPlanId : (plan?.id ?? null)}
              fillFileName={props.fillPlanId !== undefined ? null : (plan?.file_name ?? null)}
              onFill={(id) => setFillOpen(id)}
              announce={announce}
            />
          </div>
        </div>
        <div
          id={tabId(tab)}
          role="tabpanel"
          aria-labelledby={`${tabId(tab)}-tab`}
          dir={language() === "ar" ? "rtl" : "ltr"}
          hidden={folded}
          className={`min-h-0 flex-1 overflow-auto ${mode === "workspace" ? "p-3" : "px-5 py-4"}`}
        >
          {folded ? null : fillOpen ? (
            <FillPreview projectId={projectId} planId={fillOpen} announce={announce} onClose={() => setFillOpen(null)} />
          ) : tab === "changes" ? (
            <ChangesPanel
              projectId={projectId}
              view={view}
              changes={state.changes}
              stale={state.stale}
              onChanged={changed}
              onLocate={onLocate}
              announce={announce}
              onAccepted={accepted}
              onRejected={rejected}
              onCurrent={onCurrent}
            />
          ) : tab === "comments" ? (
            <CommentsPanel
              projectId={projectId}
              view={view}
              comments={state.comments}
              selection={selected?.comment ?? null}
              onChanged={changed}
              onSend={props.onSend}
              onLocate={onLocate}
              announce={announce}
            />
          ) : tab === "versions" ? (
            <VersionsPanel projectId={projectId} view={view} />
          ) : (
            <SignOff projectId={projectId} view={view} onChanged={changed} announce={announce} />
          )}
        </div>
      </div>
      <p role="status" className="sr-only">
        {status}
      </p>
    </div>
  );
}
