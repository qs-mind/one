// A Deliverable on the canvas. Zoomed in and among the six live frames, it runs Plan 6's viewer in mode "frame";
// otherwise it shows its poster (title, status, Revision, progress, open comments). Without a viewer for its kind
// (Plan 6 not merged yet) it always shows the poster.
import type { Node, NodeProps } from "@xyflow/react";
import { useCallback } from "react";
import { fill, pick, t, useLanguage } from "../../i18n";
import { viewerFor } from "../sources";
import type { DeliverableInfo, FrameKey, ViewerHandle } from "../types";
import { Frame, frameTitle, memoFrame, useCanvasActions, useDetail, type DeliverableData } from "./Frame";

/** The live viewers' handles by frame, for the cursors (Task 5): `locate(anchor)` gives a box in the viewer's own
 * unscaled pixels, relative to its root. */
export const viewerHandles = new Map<FrameKey, ViewerHandle>();

function statusLine(d: DeliverableInfo): string {
  if (d.status === "signed_off") return t("statusSignedOff");
  if (d.status === "checked") return fill(t("statusChecked"), { code: d.code ?? "" });
  return t("statusDraft");
}

const progressLine = (d: DeliverableInfo) => d.progress && fill(t("progressOf"), d.progress);

function CommentsPin({ n }: { n: number }) {
  return (
    <span className="flex shrink-0 items-center gap-1 text-copper">
      <svg aria-hidden="true" viewBox="0 0 12 12" className="h-3 w-3 fill-current">
        <path d="M6 0a5 5 0 0 1 5 5c0 3.5-5 7-5 7S1 8.5 1 5a5 5 0 0 1 5-5z" />
      </svg>
      <bdi>{fill(t("openCommentsCount"), { n })}</bdi>
    </span>
  );
}

/** The strip: status, Revision, progress and open comments, each only when known. */
function StripMeta({ d }: { d: DeliverableInfo }) {
  return (
    <span className="flex min-w-0 shrink items-center gap-2 truncate text-slate">
      <bdi className="shrink-0">{statusLine(d)}</bdi>
      {d.revision !== null && <bdi className="shrink-0">{fill(t("reviewRev"), { n: d.revision })}</bdi>}
      {d.progress && <bdi className="shrink-0 tabular-nums">{progressLine(d)}</bdi>}
      {d.open_comments > 0 && <CommentsPin n={d.open_comments} />}
    </span>
  );
}

function Poster({ d }: { d: DeliverableInfo }) {
  return (
    <div className="flex h-full flex-col justify-center gap-2 p-6 text-lg">
      <p dir="auto" className="text-2xl font-semibold">
        {d.title}
      </p>
      {/* The frame reads in the Deliverable's language; these lines are in the page language, so each is isolated */}
      <p>
        <bdi>{statusLine(d)}</bdi>
        {d.revision !== null && (
          <>
            {" · "}
            <bdi>{fill(t("reviewRev"), { n: d.revision })}</bdi>
          </>
        )}
      </p>
      {d.desk && (
        <p className="text-slate">
          <bdi>{fill(t("fromDesk"), { desk: pick(d.desk) })}</bdi>
        </p>
      )}
      {d.off_desk && (
        <p className="text-slate">
          <bdi>{t("statusOffDesk")}</bdi>
        </p>
      )}
      {d.same_provider && (
        <p className="text-slate">
          <bdi>{t("statusSameProvider")}</bdi>
        </p>
      )}
      {d.progress && (
        <p className="tabular-nums">
          <bdi>{progressLine(d)}</bdi>
        </p>
      )}
      {d.open_comments > 0 && <CommentsPin n={d.open_comments} />}
    </div>
  );
}

function DeliverableFrameView(props: NodeProps<Node<DeliverableData, "deliverable">>) {
  useLanguage();
  const actions = useCanvasActions();
  const detail = useDetail();
  const key = props.id as FrameKey;
  const d = props.data.deliverable;
  const Viewer = viewerFor(d.kind);
  const keep = useCallback(
    (handle: ViewerHandle | null) => {
      if (!handle) return;
      viewerHandles.set(key, handle);
      return () => {
        viewerHandles.delete(key);
      };
    },
    [key],
  );
  const live = Viewer && detail === "live" && props.data.live;

  return (
    <Frame
      id={key}
      selected={props.selected}
      collapsed={props.data.collapsed}
      title={frameTitle({ type: "deliverable", data: props.data })}
      dir={d.language === "ar" ? "rtl" : "ltr"}
      lang={d.language}
      meta={<StripMeta d={d} />}
      onOpenFull={() => actions.openFull(d.id)}
      scrolls={!!live}
    >
      {live ? (
        <Viewer
          ref={keep}
          projectId={actions.projectId}
          deliverableId={d.id}
          mode="frame"
          onSelection={(anchor, label) => actions.viewerSelection(key, anchor, label)}
        />
      ) : (
        <Poster d={d} />
      )}
    </Frame>
  );
}

export const DeliverableFrame = memoFrame(DeliverableFrameView);
