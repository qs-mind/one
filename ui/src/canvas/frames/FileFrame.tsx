// One file of Project Records on the canvas. A PDF shows its page as an image the core renders in memory, with page
// buttons and a switch to the page's text; other files show the text pieces One read, with their sheet and row.
// "Close" removes the frame only: the file stays in Project Records.
import { useStore, type Node, type NodeProps } from "@xyflow/react";
import { useEffect, useState } from "react";
import { dir, fill, t, useLanguage } from "../../i18n";
import type { FilePiece } from "../../project/types";
import { Frame, frameTitle, memoFrame, useCanvasActions, useDetail, type FileData } from "./Frame";
import { FileName } from "../../ui/FileName";
import { Segmented } from "../../ui/Segmented";
import { fileKey, TARGET } from "../../sources/targets";

/** Page images come in two widths: enough for the frame on screen, never more (decision 13). */
const SMALL = 600;
const LARGE = 1400;

function where(locator: FilePiece["locator"]): string | undefined {
  const { page, sheet, row, line } = locator;
  if (page !== undefined) return fill(t("page"), { page });
  if (sheet !== undefined && row !== undefined) return fill(t("sheetRow"), { sheet, row });
  if (row !== undefined) return fill(t("row"), { row });
  if (line !== undefined) return fill(t("line"), { line });
  return undefined;
}

type Image = { url: string } | "failed" | null;

function FileFrameView(props: NodeProps<Node<FileData, "file">>) {
  useLanguage();
  const { sources } = useCanvasActions();
  const detail = useDetail();
  const { file, collapsed } = props.data;
  const frameWidth = props.width ?? 480;
  const width = useStore((s) => (s.transform[2] * frameWidth * (globalThis.devicePixelRatio || 1) > SMALL ? LARGE : SMALL));
  const [pages, setPages] = useState<number | null>(null);
  const [page, setPage] = useState(props.data.page ?? 1);
  const [mode, setMode] = useState<"image" | "text">("image");
  const [image, setImage] = useState<Image>(null);
  const [pieces, setPieces] = useState<FilePiece[] | null>(null);

  useEffect(() => {
    if (props.data.page) setPage(props.data.page); // an answer or the palette asked for this page
  }, [props.data.page]);

  useEffect(() => {
    let live = true;
    sources.pages(file.id).then(
      (n) => live && setPages(n),
      () => live && setPages(0),
    );
    return () => {
      live = false;
    };
  }, [sources, file.id]);

  const showImage = pages !== null && pages > 0 && mode === "image" && detail === "live";
  useEffect(() => {
    if (!showImage) return;
    let live = true;
    setImage(null);
    sources.pageImage(file.id, page, width).then(
      (url) => live && setImage({ url }),
      () => live && setImage("failed"),
    );
    return () => {
      live = false;
    };
  }, [sources, file.id, page, width, showImage]);

  const showText = pages !== null && (pages === 0 || mode === "text") && detail === "live";
  useEffect(() => {
    if (!showText) return;
    let live = true;
    setPieces(null);
    sources.fileText(file.id, pages ? page : undefined).then(
      (got) => live && setPieces(got),
      () => live && setPieces([]),
    );
    return () => {
      live = false;
    };
  }, [sources, file.id, page, pages, showText]);

  const pageOf = pages ? fill(t("sheetPageOf"), { page, pages }) : null;
  const button =
    "rounded-lg border border-ink/20 px-3 py-1 hover:border-ink disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-ink";

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
        <div className="flex min-h-full flex-col">
          {pages !== null && pages > 0 && (
            <div className="flex items-center gap-3 bg-stone/60 px-5 py-2">
              <button type="button" className={button} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t("sheetPreviousPage")}
              </button>
              <span className="tabular-nums">{pageOf}</span>
              <button type="button" className={button} disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                {t("sheetNextPage")}
              </button>
              <Segmented<"image" | "text">
                label={t("pageView")}
                options={[
                  { value: "image", label: t("pageViewImage") },
                  { value: "text", label: t("pageViewText") },
                ]}
                value={mode}
                onChange={setMode}
                className="nodrag ms-auto"
              />
            </div>
          )}
          {showImage &&
            (image === "failed" ? (
              <p role="alert" className="px-5 py-3 text-copper">
                {t("pageNotShown")}
              </p>
            ) : (
              image && (
                <img
                  src={image.url}
                  alt={pageOf ?? file.name}
                  className="block w-full"
                  draggable={false}
                  {...{ [TARGET]: fileKey(file.id, { page }) }} // a number from this page draws its source line here
                />
              )
            ))}
          {showText &&
            pieces &&
            (pieces.length === 0 ? (
              <p className="px-5 py-3 text-slate">{pages ? t("pageScanned") : t("fileNoText")}</p>
            ) : (
              <ul className="flex flex-col divide-y divide-stone">
                {pieces.map((piece, index) => (
                  // a number from this sheet row, line or page draws its source line here, and is marked here when opened
                  <li key={index} className="flex flex-col gap-1 px-5 py-3" {...{ [TARGET]: fileKey(file.id, piece.locator) }}>
                    {!pages && where(piece.locator) && <span className="text-slate">{where(piece.locator)}</span>}
                    <span dir="auto" className="whitespace-pre-wrap">
                      {piece.text}
                    </span>
                  </li>
                ))}
              </ul>
            ))}
        </div>
      )}
    </Frame>
  );
}

export const FileFrame = memoFrame(FileFrameView);
