// One file of Project Records on the canvas. A PDF shows its page as an image the core renders in memory, with page
// buttons and a switch to the page's text; other files show the text pieces One read, with their sheet and row.
// "Close" removes the frame only: the file stays in Project Records. Zoomed in, the body is the workspace's FileDoc.
import { useStore, type Node, type NodeProps } from "@xyflow/react";
import { dir, useLanguage } from "../../i18n";
import { Frame, frameTitle, memoFrame, useCanvasActions, useDetail, type FileData } from "./Frame";
import { FileName } from "../../ui/FileName";
import { FilePages, LARGE, SMALL, useFilePage } from "../../workspace/docs/FileDoc";

function FileFrameView(props: NodeProps<Node<FileData, "file">>) {
  useLanguage();
  const { sources } = useCanvasActions();
  const detail = useDetail();
  const { file, collapsed } = props.data;
  const frameWidth = props.width ?? 480;
  const width = useStore((s) => (s.transform[2] * frameWidth * (globalThis.devicePixelRatio || 1) > SMALL ? LARGE : SMALL));
  const state = useFilePage(sources, file.id, props.data.page);
  const { pageOf } = state;

  return (
    <Frame
      id={props.id as `file:${string}`}
      selected={props.selected}
      collapsed={collapsed}
      title={frameTitle({ type: "file", data: props.data })}
      dir={dir()}
      closable
      scrolls={detail === "live"}
      meta={pageOf && <bdi className="shrink-0 text-slate">{pageOf}</bdi>}
    >
      {detail !== "live" ? (
        <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
          <FileName name={file.name} className="text-lg font-semibold break-words" />
          {pageOf && <span className="text-slate">{pageOf}</span>}
        </div>
      ) : (
        <FilePages sources={sources} fileId={file.id} state={state} width={width} inFrame />
      )}
    </Frame>
  );
}

export const FileFrame = memoFrame(FileFrameView);
