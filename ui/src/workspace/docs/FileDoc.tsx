// One file of Project Records. A PDF shows its page as an image the core renders in memory, with page buttons and a
// switch to the page's text; other files show the text pieces ONE read, with their sheet and row.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { dir, fill, t, useLanguage } from "../../i18n";
import type { FilePiece, ProjectSources } from "../../project/types";
import { fileKey, TARGET } from "../../sources/targets";
import { Segmented } from "../../ui/Segmented";

/** Page images come in two widths: enough for the file on screen, never more (decision 13). */
export const SMALL = 600;
export const LARGE = 1400;
/** How long the file's room must stay the same before its width is measured again, in ms. */
const RESIZE_SETTLE_MS = 150;

function where(locator: FilePiece["locator"]): string | undefined {
  const { page, sheet, row, line } = locator;
  if (page !== undefined) return fill(t("page"), { page });
  if (sheet !== undefined && row !== undefined) return fill(t("sheetRow"), { sheet, row });
  if (row !== undefined) return fill(t("row"), { row });
  if (line !== undefined) return fill(t("line"), { line });
  return undefined;
}

export type FilePage = {
  /** The number of pages; 0 when the file is not a PDF, null until known. */
  pages: number | null;
  page: number;
  setPage(update: (page: number) => number): void;
  mode: "image" | "text";
  setMode(mode: "image" | "text"): void;
  /** «صفحة 3 من 18», or null for a file with no pages. */
  pageOf: string | null;
};

/** The file's pages and the page shown; `asked` (an answer or the palette asked for this page) moves to it. */
export function useFilePage(sources: ProjectSources, fileId: string, asked?: number): FilePage {
  const [pages, setPages] = useState<number | null>(null);
  const [page, setPage] = useState(asked ?? 1);
  const [mode, setMode] = useState<"image" | "text">("image");

  useEffect(() => {
    if (asked) setPage(asked);
  }, [asked]);

  useEffect(() => {
    let live = true;
    sources.pages(fileId).then(
      (n) => live && setPages(n),
      () => live && setPages(0),
    );
    return () => {
      live = false;
    };
  }, [sources, fileId]);

  const pageOf = pages ? fill(t("sheetPageOf"), { page, pages }) : null;
  return { pages, page, setPage, mode, setMode, pageOf };
}

type Image = { url: string } | "failed" | null;

/** The file's live body: the page buttons and the image, or the text ONE read. */
export function FilePages({
  sources,
  fileId,
  state,
  width,
}: {
  sources: ProjectSources;
  fileId: string;
  state: FilePage;
  width: number;
}) {
  useLanguage();
  const { pages, page, setPage, mode, setMode, pageOf } = state;
  const [image, setImage] = useState<Image>(null);
  const [pieces, setPieces] = useState<FilePiece[] | null>(null);

  const showImage = pages !== null && pages > 0 && mode === "image";
  useEffect(() => {
    if (!showImage) return;
    let live = true;
    setImage(null);
    sources.pageImage(fileId, page, width).then(
      (url) => live && setImage({ url }),
      () => live && setImage("failed"),
    );
    return () => {
      live = false;
    };
  }, [sources, fileId, page, width, showImage]);

  const showText = pages !== null && (pages === 0 || mode === "text");
  useEffect(() => {
    if (!showText) return;
    let live = true;
    setPieces(null);
    sources.fileText(fileId, pages ? page : undefined).then(
      (got) => live && setPieces(got),
      () => live && setPieces([]),
    );
    return () => {
      live = false;
    };
  }, [sources, fileId, page, pages, showText]);

  const button =
    "rounded-lg border border-ink/20 px-3 py-1 hover:border-ink disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-ink";

  return (
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
            className="ms-auto"
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
              alt={pageOf ?? ""}
              className="block w-full"
              draggable={false}
              {...{ [TARGET]: fileKey(fileId, { page }) }} // a number from this page draws its source line here
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
              <li key={index} className="flex flex-col gap-1 px-5 py-3" {...{ [TARGET]: fileKey(fileId, piece.locator) }}>
                {!pages && where(piece.locator) && <span className="text-slate">{where(piece.locator)}</span>}
                <span dir="auto" className="whitespace-pre-wrap">
                  {piece.text}
                </span>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

/** The file as the open document, at `page` when one is asked for. */
export function FileDoc({ sources, fileId, page }: { sources: ProjectSources; fileId: string; page?: number }) {
  useLanguage();
  const state = useFilePage(sources, fileId, page);
  const root = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(SMALL);
  // measured again when the room changes (the chat folds, the window resizes), settled for 150 ms before a reload
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth * (globalThis.devicePixelRatio || 1) > SMALL ? LARGE : SMALL);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sizes = new ResizeObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(measure, RESIZE_SETTLE_MS);
    });
    sizes.observe(el);
    return () => {
      clearTimeout(timer);
      sizes.disconnect();
    };
  }, []);
  return (
    <div ref={root} dir={dir()} className="h-full overflow-auto bg-paper text-ink">
      <FilePages sources={sources} fileId={fileId} state={state} width={width} />
    </div>
  );
}
