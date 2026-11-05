// One Deliverable, as the viewer registry gives it to the canvas and the chat's side panel. It loads its own data
// and loads it again when the project's live stream says the Deliverable changed. In `mode="frame"` it is the
// Sheet or Document viewer only, filling its container; in `mode="full"` it is the review board: the viewer, then
// Changes, Comments, Versions and Close-out, with the exports. Everything it draws stays inside its own box.
import { useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { Anchor, ViewerProps } from "../canvas/types";
import { fill, language, pick, t, useLanguage } from "../i18n";
import { ChangesPanel } from "../review/ChangesPanel";
import { CommentsPanel } from "../review/CommentsPanel";
import { ExportMenu } from "../review/ExportMenu";
import { FillPreview } from "../review/FillPreview";
import { rangePlace } from "../review/place";
import { SignOff } from "../review/SignOff";
import { VersionsPanel } from "../review/VersionsPanel";
import { DocumentViewer, type DocumentHandle } from "../viewers/document/DocumentViewer";
import type { TextAnchor } from "../viewers/document/plate";
import { SheetViewer, type SheetHandle, type SheetRange } from "../viewers/sheet/SheetViewer";
import { deliverablesApi } from "./api";
import type { CommentAnchor, FillPlanInfo, View } from "./types";
import { useDeliverable, type Subscribe } from "./useDeliverable";

export type DeliverableViewerProps = ViewerProps & {
  /** Sends a message to the Lead QS, as the chat does ("Fix it"). */
  onSend?: (text: string) => void;
  /** The Fill Plan of the client's own file; left out, the board finds the newest one itself. */
  fillPlanId?: string | null;
  onToggleFullScreen?: () => void;
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

  // The board finds the Sheet's newest Fill Plan, and looks again each time the Deliverable is loaded (a plan the
  // Lead QS saves is announced on the live stream).
  const findPlan = mode === "full" && view?.kind === "sheet" && props.fillPlanId === undefined;
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

  /** Where the anchor is, relative to this viewer's root, in its own unscaled pixels (it may sit in a scaled frame). */
  function locate(anchor: Anchor): DOMRect | null {
    const inner = (view?.kind === "sheet" ? sheet.current : doc.current)?.locate(anchor) ?? null;
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

  if (!view) {
    return (
      <div ref={root} className="flex h-full w-full items-center justify-center bg-paper p-4 text-slate">
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
      />
    );

  const tabs: [Tab, string][] = [
    ["changes", t("reviewChanges")],
    ["comments", t("reviewComments")],
    ["versions", t("reviewVersions")],
    ["closeout", t("reviewCloseOut")],
  ];
  const tabId = (key: Tab) => `review-${view.id}-${key}`;
  const onLocate = (anchor: Anchor) => void locate(anchor);

  return (
    <div ref={root} className="relative flex h-full w-full min-h-0 flex-col bg-paper text-ink">
      <div ref={body} className={mode === "full" ? "min-h-0 flex-[3_1_0%]" : "min-h-0 flex-1"}>
        {viewer}
      </div>
      {mode === "full" && (
        <div className="flex min-h-0 flex-[2_1_0%] flex-col bg-stone/50">
          <div className="flex flex-wrap items-center gap-3 px-5 pb-1 pt-3">
            <div role="tablist" aria-label={t("reviewPanels")} className="flex flex-wrap gap-1">
              {tabs.map(([key, label]) => (
                <button
                  key={key}
                  id={`${tabId(key)}-tab`}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  aria-controls={tabId(key)}
                  className={`rounded-lg px-3 py-1.5 ${tab === key ? "bg-ink text-paper" : "hover:bg-stone"}`}
                  onClick={() => {
                    setTab(key);
                    setFillOpen(null);
                  }}
                >
                  {label}
                  {key === "changes" && view.pending > 0 && <bdi> ({view.pending})</bdi>}
                  {key === "comments" && view.open_comments > 0 && <bdi> ({view.open_comments})</bdi>}
                </button>
              ))}
            </div>
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
            className="min-h-0 flex-1 overflow-auto px-5 py-4"
          >
            {fillOpen ? (
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
      )}
      <p role="status" className="sr-only">
        {status}
      </p>
    </div>
  );
}
