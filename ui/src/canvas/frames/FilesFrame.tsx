// The Project files frame (files:all): every current file with what One could read in it. A click opens the file's
// own frame; files dropped on it go to Project Records.
import type { Node, NodeProps } from "@xyflow/react";
import { dir, pick, t, texts, useLanguage, type Text } from "../../i18n";
import type { FileInfo } from "../types";
import { Frame, frameTitle, memoFrame, useCanvasActions, type FilesData } from "./Frame";
import { FileName } from "../../ui/FileName";

const statusText: Record<FileInfo["status"], Text> = {
  read: texts.fileRead,
  partly_read: texts.filePartlyRead,
  stored: texts.fileStored,
  unreadable: texts.fileUnreadable,
};

function FilesFrameView(props: NodeProps<Node<FilesData, "files">>) {
  useLanguage();
  const actions = useCanvasActions();
  const { files, collapsed } = props.data;
  return (
    <Frame
      id="files:all"
      selected={props.selected}
      collapsed={collapsed}
      title={frameTitle({ type: "files", data: props.data })}
      dir={dir()}
      meta={<span className="shrink-0 text-slate tabular-nums">{files.length}</span>}
    >
      <div
        className="flex min-h-full flex-col"
        onDragOver={(event) => {
          if (!event.dataTransfer.types.includes("Files")) return;
          event.preventDefault();
          event.stopPropagation();
        }}
        onDrop={(event) => {
          event.preventDefault(); // the window must not open the file itself
          event.stopPropagation(); // added here, not opened at the drop point
          actions.addFiles(Array.from(event.dataTransfer.files));
        }}
      >
        {files.length === 0 ? (
          <p className="px-5 py-3 text-slate">{t("noFiles")}</p>
        ) : (
          <ul className="flex flex-col gap-1 px-2">
            {files.map((file) => (
              <li key={file.id}>
                <button
                  type="button"
                  onClick={() => actions.openFile(file.id)}
                  className="flex w-full flex-col items-start rounded-[10px] px-3 py-2.5 text-start hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
                >
                  <span className="flex w-full items-center justify-between gap-4">
                    <FileName name={file.name} fit />
                    <span className={`shrink-0 ${file.status === "read" ? "text-slate" : "text-copper"}`}>
                      {pick(statusText[file.status])}
                    </span>
                  </span>
                  {file.note && <span className="text-slate">{pick(file.note)}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-auto px-5 py-4 text-xs text-slate">{t("dropToAdd")}</p>
      </div>
    </Frame>
  );
}

export const FilesFrame = memoFrame(FilesFrameView);
