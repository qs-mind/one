// A client BOQ as boq_import read it: the client's own document, read only. Zoomed in, it runs the Sheet viewer with
// nothing editable; each number opens its source (the client's file, sheet, row and cell) and the jump to that
// file's frame. Otherwise it shows a poster. It reloads when the file is imported again. It is not a Deliverable.
import type { Node, NodeProps } from "@xyflow/react";
import { count, pick, t, useLanguage } from "../../i18n";
import { SheetViewer } from "../../viewers/sheet/SheetViewer";
import type { FrameKey } from "../../project/types";
import { useClientBoq } from "../../workspace/docs/ClientBoqDoc";
import { Frame, frameTitle, memoFrame, useCanvasActions, useDetail, type ClientBoqData } from "./Frame";

function ClientBoqFrameView(props: NodeProps<Node<ClientBoqData, "clientboq">>) {
  useLanguage();
  const { projectId, sources } = useCanvasActions();
  const detail = useDetail();
  const { boq, collapsed } = props.data;
  const live = detail === "live" && !collapsed;
  const loaded = useClientBoq(sources, boq.file_id, boq.at, live);
  const title = frameTitle({ type: "clientboq", data: props.data });

  const view = loaded && "view" in loaded ? loaded.view : null;
  return (
    <Frame
      id={props.id as FrameKey}
      selected={props.selected}
      collapsed={collapsed}
      title={title}
      dir={view ? (view.language === "ar" ? "rtl" : "ltr") : "auto"}
      lang={view?.language}
      meta={
        <span className="flex shrink-0 items-center gap-2 text-slate">
          <bdi>{t("clientBoqReadOnly")}</bdi>
          <bdi className="tabular-nums">{count("clientBoqItems", boq.items)}</bdi>
        </span>
      }
      scrolls={!!(live && view)}
    >
      {live && view ? (
        <SheetViewer projectId={projectId} view={{ ...view, title }} mode="frame" readOnly />
      ) : (
        <div className="flex h-full flex-col justify-center gap-2 p-6 text-lg">
          <p dir="auto" className="text-2xl font-semibold">
            {title}
          </p>
          <p>
            <bdi>{t("clientBoqReadOnly")}</bdi>
            {" · "}
            <bdi className="tabular-nums">{count("clientBoqItems", boq.items)}</bdi>
          </p>
          {live && loaded && "failed" in loaded && (
            <p role="alert" className="text-copper">
              {pick(loaded.failed)}
            </p>
          )}
          {live && !loaded && <p className="text-slate">{t("clientBoqLoading")}</p>}
        </div>
      )}
    </Frame>
  );
}

export const ClientBoqFrame = memoFrame(ClientBoqFrameView);
