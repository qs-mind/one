// One file of Project Records. A PDF shows its page as an image the core renders in memory, with page buttons and a
// switch to the page's text; other files show the text pieces ONE read, with their sheet and row.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { isNumber } from "../../deliverables/types";
import { dir, fill, t, useLanguage } from "../../i18n";
import type { FilePiece, FileSheet, Opened, ProjectSources } from "../../project/types";
import { REVEAL_WAIT_MS } from "../../sources/mark";
import { fileKey, TARGET } from "../../sources/targets";
import { Segmented } from "../../ui/Segmented";
import { type SheetHandle, SheetViewer } from "../../viewers/sheet/SheetViewer";
import type { FileRegion, PdfBox, Thread } from "../../deliverables/types";
import { PdfRegions } from "./PdfRegions";
import { FileRegionComments } from "./FileRegionComments";
import { workspaceApi } from "../api";
import { CompareDoc } from "./CompareDoc";

/** Base page widths; zoom requests proportionally sharper images, bounded by the core. */
export const SMALL = 600;
export const LARGE = 1400;
/** How long the file's room must stay the same before its width is measured again, in ms. */
const RESIZE_SETTLE_MS = 150;

function where(locator: FilePiece["locator"]): string | undefined {
  const { page, sheet, row, line, handle } = locator;
  if (page !== undefined) return fill(t("page"), { page });
  if (sheet !== undefined && row !== undefined) return fill(t("sheetRow"), { sheet: String(sheet).trim(), row }); // «مقايسة » had a space
  if (sheet !== undefined && handle !== undefined) return fill(t("drawingAt"), { sheet: String(sheet), handle: String(handle) });
  if (row !== undefined) return fill(t("row"), { row });
  if (line !== undefined) return fill(t("line"), { line });
  return undefined;
}

export type FilePage = {
  /** PDF pages or one standalone image; 0 for text/sheets, null until known. */
  pages: number | null;
  page: number;
  setPage(update: (page: number) => number): void;
  mode: "image" | "text";
  setMode(mode: "image" | "text"): void;
  /** «صفحة 3 من 18», or null for a file with no pages. */
  pageOf: string | null;
};

/** The file's pages and the page shown. Each opening of the file at a page (an answer, a number's card, the palette)
 * moves to it, the same page asked again too; a page the engineer turns to is the open document's place, so Back and
 * the project come back to it. */
export function useFilePage(sources: ProjectSources, fileId: string, opened?: Opened): FilePage {
  const [pages, setPages] = useState<number | null>(null);
  const [page, setPage] = useState(opened?.anchor?.page ?? 1);
  const [mode, setMode] = useState<"image" | "text">("image");

  useEffect(() => {
    setMode("image");
    setPage(opened?.anchor?.page ?? 1);
  }, [fileId]); // eslint-disable-line react-hooks/exhaustive-deps -- reset once per file

  const openedRef = useRef(opened);
  openedRef.current = opened;
  useEffect(() => {
    const asked = opened?.anchor?.page;
    if (asked) {
      setPage(asked);
      if (opened?.anchor?.box || opened?.anchor?.value) setMode("image");
    }
  }, [opened]);
  useEffect(() => {
    const now = openedRef.current;
    if (!now || workspaceApi.current() !== now || now.anchor?.page === page) return;
    workspaceApi.at({ ...now.anchor, page, box: undefined, value: undefined });
  }, [page]);

  useEffect(() => {
    let live = true;
    setPages(null);
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
  notice,
  opened,
  projectId,
  controls = true,
}: {
  sources: ProjectSources;
  fileId: string;
  state: FilePage;
  opened?: Opened;
  projectId?: string;
  width: number;
  controls?: boolean;
  /** Said under the page controls, a row of its own: it never covers them. */
  notice?: string | null;
}) {
  useLanguage();
  const { pages, page, setPage, mode, setMode, pageOf } = state;
  const [image, setImage] = useState<Image>(null);
  const [zoom, setZoom] = useState(1);
  const [renderWidth, setRenderWidth] = useState(width);
  useEffect(() => {
    const timer = setTimeout(() => setRenderWidth(Math.max(200, Math.min(5600, Math.round(width * zoom)))), RESIZE_SETTLE_MS);
    return () => clearTimeout(timer);
  }, [width, zoom]);
  useEffect(() => { setImage(null); }, [fileId, page]);
  const viewport = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, {x: number; y: number}>());
  const [ratio, setRatio] = useState(1);
  const [fitWidth, setFitWidth] = useState<number | null>(null);
  const changeZoom = (factor: number) => setZoom((z) => Math.max(0.25, Math.min(4, z * factor)));
  useEffect(() => { setZoom(1); }, [fileId, page]);
  useLayoutEffect(() => {
    const el = viewport.current;
    if (!el) return;
    const measure = () => {
      if (el.clientWidth && el.clientHeight) setFitWidth(Math.min(el.clientWidth, el.clientHeight * ratio));
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(el);
    const wheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      changeZoom(event.deltaY < 0 ? 1.25 : 0.8);
    };
    el.addEventListener("wheel", wheel, {passive: false});
    return () => { observer?.disconnect(); el.removeEventListener("wheel", wheel); };
  }, [ratio, mode, pages]);
  const [pieces, setPieces] = useState<FilePiece[] | null>(null);

  const [geometry, setGeometry] = useState<{width: number; height: number; boxes: PdfBox[]} | null>(null);
  const [regionFailed, setRegionFailed] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [selection, setSelection] = useState<FileRegion | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const asked = opened?.anchor?.page === page ? opened.anchor : null;
  const sourceBox = asked?.box;
  const value = sourceBox ? undefined : asked?.value;
  useEffect(() => {
    let live = true;
    setGeometry(null);
    setRegionFailed(false);
    setSelection(null);
    setSelecting(false);
    if (pages && sources.pageBoxes) {
      void sources.pageBoxes(fileId, page, value).then(
        (got) => { if (live) setGeometry(got); },
        () => { if (live) setRegionFailed(true); },
      );
    }
    return () => { live = false; };
  }, [sources, fileId, pages, page, value, opened]);
  const commentBoxes = threads.flatMap((thread) => {
    const anchor = thread.anchor_now;
    return thread.status === "open" && "kind" in anchor && anchor.kind === "file_region" && anchor.file_id === fileId && anchor.page === page
      ? [anchor.box] : [];
  });
  const boxes = [...commentBoxes, ...(selection ? [selection.box] : sourceBox ? [sourceBox] : geometry?.boxes ?? [])]
    .filter((box, index, all) => all.findIndex((other) => other.every((n, i) => n === box[i])) === index);

  const showImage = pages !== null && pages > 0 && mode === "image";
  useEffect(() => {
    if (!showImage) return;
    let live = true;
    sources.pageImage(fileId, page, renderWidth).then(
      (url) => live && setImage({ url }),
      () => live && setImage("failed"),
    );
    return () => {
      live = false;
    };
  }, [sources, fileId, page, renderWidth, showImage]);

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
    <div className="flex h-full min-h-0 flex-col">
      {controls && pages !== null && pages > 0 && (
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
      {showImage && (
        <div className="flex shrink-0 items-center gap-2 px-5 py-2">
          <button type="button" className={button} disabled={zoom <= 0.25} onClick={() => changeZoom(0.8)}>{t("fileZoomOut")}</button>
          <button type="button" className={button} disabled={zoom >= 4} onClick={() => changeZoom(1.25)}>{t("fileZoomIn")}</button>
          <button type="button" className={button} onClick={() => { setZoom(1); viewport.current?.scrollTo?.(0, 0); }}>{t("fileFit")}</button>
        </div>
      )}
      {showImage && projectId && geometry && (
        <div className="flex items-center gap-3 px-5 py-2">
          <button type="button" className={button} aria-pressed={selecting} onClick={() => setSelecting(!selecting)}>
            {t("regionSelect")}
          </button>
          {selecting && <span>{t("regionDrag")}</span>}
        </div>
      )}
      {showImage && (regionFailed || (value && geometry && !geometry.boxes.length)) && (
        <p role="status" className="px-5 py-2 text-slate">{t(regionFailed ? "regionUnavailable" : "regionValueMissing")}</p>
      )}
      {notice && (
        <p role="status" className={`px-5 pb-2 text-sm text-slate ${pages ? "bg-stone/60" : "pt-2"}`}>
          {notice}
        </p>
      )}
      {showImage && <div ref={viewport} data-testid="picture-pan" dir="ltr"
        className="min-h-0 flex-1 overflow-auto" style={{touchAction: selecting ? "auto" : "none"}}
        onPointerDown={(event) => {
          if (selecting || event.button !== 0) return;
          pointers.current.set(event.pointerId, {x:event.clientX, y:event.clientY});
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => {
          const before = pointers.current.get(event.pointerId);
          if (!before) return;
          const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
          if (other) {
            const oldDistance = Math.hypot(before.x-other.x, before.y-other.y);
            const distance = Math.hypot(event.clientX-other.x, event.clientY-other.y);
            if (oldDistance > 0) changeZoom(distance / oldDistance);
          } else {
            event.currentTarget.scrollLeft -= event.clientX-before.x;
            event.currentTarget.scrollTop -= event.clientY-before.y;
          }
          pointers.current.set(event.pointerId, {x:event.clientX,y:event.clientY});
        }}
        onPointerUp={(event) => { pointers.current.delete(event.pointerId); }}
        onPointerCancel={(event) => { pointers.current.delete(event.pointerId); }}
        onLostPointerCapture={(event) => { pointers.current.delete(event.pointerId); }}
      ><div style={{width: fitWidth ? fitWidth * zoom : `${zoom * 100}%`, marginInline: zoom <= 1 ? "auto" : undefined}}>
        {(image === "failed" ? (
          <p role="alert" className="px-5 py-3 text-copper">
            {t("pageNotShown")}
          </p>
        ) : (
          image && (
            <PdfRegions
              width={geometry?.width ?? 1} height={geometry?.height ?? 1} boxes={geometry ? boxes : []}
              onSelect={selecting && geometry ? (box) => {
                setSelection({ kind: "file_region", file_id: fileId, page, box });
                setSelecting(false);
              } : undefined}
            >
              <img
                src={image.url} alt={pageOf ?? ""} className="block w-full" draggable={false}
                onLoad={(event) => { const img = event.currentTarget; if (img.naturalHeight) setRatio(img.naturalWidth / img.naturalHeight); }}
                {...{ [TARGET]: fileKey(fileId, { page }) }}
              />
            </PdfRegions>
          )
        ))}</div></div>}
      {projectId && pages !== null && pages > 0 && (
        <FileRegionComments key={fileId} sources={sources} projectId={projectId} fileId={fileId}
          selection={selection} onAdded={() => setSelection(null)} onThreads={setThreads} />
      )}
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

/** A spreadsheet's sheet in the Sheet viewer, read only, with a tab for each sheet (a hidden one says so). Each opening
 * at a cell (a source) shows its sheet and scrolls to the cell; the source mark then finds its row. */
function SheetFile({ projectId, sources, fileId, first, opened, notice }: {
  projectId: string;
  sources: ProjectSources;
  fileId: string;
  first: FileSheet;
  notice?: string | null;
  opened?: Opened;
}) {
  useLanguage();
  const [view, setView] = useState(first);
  const handle = useRef<SheetHandle>(null);
  const asked = opened?.anchor?.sheet;
  async function show(name: string) {
    if (name === view.sheet) return;
    const got = await sources.fileSheet(fileId, name).catch(() => null);
    if (got) setView(got);
  }
  useEffect(() => {
    if (asked !== undefined) void show(asked);
  }, [opened]); // eslint-disable-line react-hooks/exhaustive-deps -- each opening once
  useEffect(() => {
    const anchor = opened?.anchor;
    if (!anchor?.row || (anchor.sheet !== undefined && anchor.sheet !== view.sheet)) return;
    let live = true;
    void (async () => {
      const started = Date.now();
      while (live && !handle.current?.locate({ row: anchor.row, column: anchor.column }) && Date.now() - started < REVEAL_WAIT_MS)
        await new Promise((resolve) => requestAnimationFrame(resolve));
    })();
    return () => {
      live = false;
    };
  }, [opened, view]);
  // Every visible cell carries its row target: horizontal virtualization may remove the first column.
  const shown = useMemo<FileSheet>(() => {
    const place = (row: string): Record<string, string> => (view.sheet ? { sheet: view.sheet, row } : { line: row });
    return {
      ...view,
      rows: view.rows.map((row) => ({
        ...row,
        cells: Object.fromEntries(Object.entries(row.cells).map(([key, cell]) => [
          key, !cell || isNumber(cell) ? cell : { ...cell, at: fileKey(fileId, place(row.code ?? "")) },
        ])),
      })),
    };
  }, [view, fileId]);
  const tab = "whitespace-nowrap rounded-t-md border border-b-0 px-3 py-1 text-sm focus-visible:outline-2 focus-visible:outline-ink";
  return (
    <div className="flex h-full flex-col bg-paper">
      {notice && (
        <p role="status" className="px-5 py-2 text-sm text-slate">
          {notice}
        </p>
      )}
      <div className="min-h-0 flex-1">
        <SheetViewer key={view.id} ref={handle} projectId={projectId} view={shown} mode="workspace" readOnly virtualize />
      </div>
      {view.sheets.length > 1 && (
        <div role="tablist" aria-label={t("fileSheets")} className="flex shrink-0 gap-1 overflow-x-auto border-t border-stone px-3 pt-1">
          {view.sheets.map((s) => (
            <button
              key={s.name}
              type="button"
              role="tab"
              aria-selected={s.name === view.sheet}
              onClick={() => void show(s.name)}
              className={`${tab} ${s.name === view.sheet ? "border-ink bg-paper" : "border-stone text-slate hover:text-ink"}`}
            >
              <bdi>{s.name.trim()}</bdi>
              {s.hidden && <span className="ms-1.5 text-xs text-slate">{t("sheetHidden")}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** The file as the open document, at its anchor's page when one is asked for. A spreadsheet opens as its sheets; a
 * file the sheet reader cannot open shows the text ONE read. */
export function FileDoc({ projectId, sources, fileId, opened, notice }: {
  projectId?: string;
  sources: ProjectSources;
  fileId: string;
  opened?: Opened;
  notice?: string | null;
}) {
  useLanguage();
  const [comparing, setComparing] = useState(false);
  const state = useFilePage(sources, fileId, opened);
  const [drawing, setDrawing] = useState(false);
  useEffect(() => {
    let live = true;
    sources.files().then((files) => {
      if (live) setDrawing(/\.(dwg|dxf)$/i.test(files.find((f) => f.id === fileId)?.name ?? ""));
    }, () => {});
    return () => { live = false; };
  }, [sources, fileId]);
  // undefined while asked; null for no sheet (a PDF, a text file, or one the sheet reader cannot open)
  const [sheet, setSheet] = useState<FileSheet | null | undefined>(undefined);
  useEffect(() => {
    if (state.pages === null) return;
    if (state.pages > 0 || !projectId) return setSheet(null);
    let live = true;
    sources.fileSheet(fileId).then(
      (got) => live && setSheet(got),
      () => live && setSheet(null),
    );
    return () => {
      live = false;
    };
  }, [sources, fileId, projectId, state.pages]);
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
  if (comparing && projectId) return <CompareDoc projectId={projectId} fileId={fileId} sources={sources} onClose={() => setComparing(false)} />;
  if (sheet && projectId)
    return <SheetFile projectId={projectId} sources={sources} fileId={fileId} first={sheet} opened={opened} notice={notice} />;
  return (
    <div ref={root} dir={dir()} className="h-full overflow-auto bg-paper text-ink">
      {drawing && <p role="status" className="px-5 py-3 text-slate">{t("drawingNoPreview")}</p>}
      {projectId && (state.pages ?? 0) > 0 && <button type="button" className="px-5 py-2 text-copper" onClick={() => setComparing(true)}>{t("compareOpen")}</button>}
      {sheet === null && <FilePages sources={sources} fileId={fileId} state={state} width={width} notice={notice} opened={opened} projectId={projectId} />}
    </div>
  );
}
