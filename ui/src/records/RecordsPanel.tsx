// Project Records for the open project: drop or add files, see what One could read in each, and search them.
// Files go to the core one at a time as their raw bytes; the page never sends a file path.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { fill, language, pick, t, type Text, texts, useLanguage } from "../i18n";
import type { FileInfo } from "../canvas/types";
import { coreLine } from "../core";
import { MeaningStatus } from "./MeaningStatus";
import { useProject } from "./project";
import { FileName } from "../ui/FileName";

type Hit = {
  chunk_id?: number;
  file_id: string;
  file_name: string;
  locator: Record<string, string | number>;
  text: string;
};
type Found =
  | { state: "found"; note: Text | null; results: Hit[]; reordering: boolean }
  | { state: "failed"; line: Text };

// Search asks the core for its top 30 and shows 10 at once; the reranker then reorders those 30 by meaning.
const ASKED = 30;
const SHOWN = 10;

const statusText: Record<FileInfo["status"], Text> = {
  read: texts.fileRead,
  partly_read: texts.filePartlyRead,
  stored: texts.fileStored,
  unreadable: texts.fileUnreadable,
};

/** Where a result sits in its file: «صفحة 3», "Sheet BOQ, row 23". */
function where({ page, sheet, row, line }: Hit["locator"]): string | undefined {
  if (page !== undefined) return fill(t("page"), { page });
  if (sheet !== undefined && row !== undefined) return fill(t("sheetRow"), { sheet, row });
  if (row !== undefined) return fill(t("row"), { row });
  if (line !== undefined) return fill(t("line"), { line });
  return undefined;
}

/** A hidden-text flag, as GET /projects/{p}/files/{f}/flags sends it (core/qsone/records/hidden.py). */
type Flag = {
  kind: string;
  locator: Record<string, string | number | (string | number)[]>;
  excerpt: string;
  count: number;
};
/** A file in the list, with how many hidden-text flags it has. */
type RecordsFile = FileInfo & { flags?: number };

const flagText: Record<string, Text> = {
  white_text: texts.flagWhite,
  tiny_text: texts.flagTiny,
  invisible_text: texts.flagInvisible,
  off_page: texts.flagOffPage,
  hidden_sheet: texts.flagHiddenSheet,
  hidden_rows: texts.flagHiddenRows,
  hidden_columns: texts.flagHiddenColumns,
  hidden_element: texts.flagHiddenElement,
  ai_instruction: texts.flagAiOrder,
};

/** Where a flag sits: a page, a sheet's rows, columns or cells, a Word paragraph or table row, a drawing layer. */
function flagWhere(locator: Flag["locator"]): string | undefined {
  const { sheet, rows, columns, cells, paragraph, table, row, layer } = locator;
  const list = (items: Flag["locator"][string]) => [items].flat().join(language() === "ar" ? "، " : ", ");
  if (sheet !== undefined) {
    if (rows !== undefined) return fill(t("flagSheetRows"), { sheet: list(sheet), rows: list(rows) });
    if (columns !== undefined) return fill(t("flagSheetColumns"), { sheet: list(sheet), columns: list(columns) });
    if (cells !== undefined) return fill(t("flagSheetCells"), { sheet: list(sheet), cells: list(cells) });
    if (row === undefined) return fill(t("flagSheet"), { sheet: list(sheet) });
  }
  if (table !== undefined && row !== undefined) return fill(t("flagTableRow"), { table: list(table), row: list(row) });
  if (paragraph !== undefined) return fill(t("flagParagraph"), { paragraph: list(paragraph) });
  if (layer !== undefined) return fill(t("flagLayer"), { layer: list(layer) });
  return where(locator as Hit["locator"]); // a page, a sheet's row, a line
}

const warningIcon = (
  <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 shrink-0 fill-current">
    <path d="M8 1.5 15 14.5H1L8 1.5Zm-.75 5v4h1.5v-4h-1.5Zm0 5.25v1.5h1.5v-1.5h-1.5Z" />
  </svg>
);

/** The copper hidden-text mark on a flagged file; pressing it lists the flags, read from the core the first time. */
function HiddenText({ projectId, fileId }: { projectId: string; fileId: string }) {
  const [open, setOpen] = useState(false);
  const [flags, setFlags] = useState<Flag[] | "failed">();

  async function toggle() {
    setOpen(!open);
    if (open || Array.isArray(flags)) return;
    setFlags(undefined);
    const response = await api(`/projects/${projectId}/files/${fileId}/flags`).catch(() => undefined);
    const body = response?.ok
      ? ((await response.json().catch(() => undefined)) as { flags?: Flag[] } | undefined)
      : undefined;
    setFlags(body?.flags ?? "failed");
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => void toggle()}
        className="flex items-center gap-1 self-start text-copper underline-offset-2 hover:underline"
      >
        {warningIcon}
        {t("hiddenText")}
      </button>
      {open && (
        <div className="flex flex-col gap-1 rounded-md border border-copper px-3 py-2">
          <p>{t("hiddenTextWhy")}</p>
          {flags === "failed" && (
            <p role="alert" className="text-copper">
              {t("flagsFailed")}
            </p>
          )}
          {Array.isArray(flags) && (
            <ul aria-label={t("hiddenText")} className="flex flex-col gap-1">
              {flags.map((flag, index) => (
                <li key={index} className="flex flex-col">
                  <span className="flex flex-wrap gap-x-2">
                    <span className="font-semibold">{pick(flagText[flag.kind] ?? texts.hiddenText)}</span>
                    <span className="text-slate">{flagWhere(flag.locator)}</span>
                  </span>
                  <span dir="auto" className="whitespace-pre-wrap break-words">
                    {flag.excerpt}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Sends one file to Project Records as its raw bytes; answers what the core made of it, or its refusal. */
export async function uploadFile(
  projectId: string,
  file: File,
): Promise<{ ok: true; info: FileInfo } | { ok: false; line: Text }> {
  const response = await api(`/projects/${projectId}/files?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    body: file,
  }).catch(() => undefined);
  if (response?.ok) return { ok: true, info: (await response.json()) as FileInfo };
  return { ok: false, line: await coreLine(response, texts.fileNotAdded) };
}

export function RecordsPanel({ onClose, onPickProject }: { onClose: () => void; onPickProject: () => void }) {
  useLanguage();
  const title = useId();
  const project = useProject();
  const chooser = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<RecordsFile[]>();
  const [filesFailed, setFilesFailed] = useState<Text>();
  const [adding, setAdding] = useState(false);
  const [problems, setProblems] = useState<{ name: string; line: Text }[]>([]);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [found, setFound] = useState<Found>();
  const turn = useRef<AbortController>(undefined); // the latest search; a newer one aborts its reordering
  const id = project?.id;

  useEffect(() => {
    setFiles(undefined);
    setFilesFailed(undefined);
    setProblems([]);
    setFound(undefined);
    if (!id) return;
    let live = true;
    void (async () => {
      const response = await api(`/projects/${id}/files`).catch(() => undefined);
      if (!live) return;
      if (response?.ok) setFiles(((await response.json()) as { files: FileInfo[] }).files);
      else setFilesFailed(await coreLine(response, texts.filesFailed));
    })();
    return () => {
      live = false;
      turn.current?.abort();
    };
  }, [id]);

  async function add(chosen: File[]) {
    if (!id || chosen.length === 0) return;
    setAdding(true);
    setProblems([]);
    for (const file of chosen) {
      const added = await uploadFile(id, file);
      if (added.ok) {
        const { info } = added;
        // the newest first; a new version takes the place of the one it replaces
        setFiles((list = []) => [info, ...list.filter((f) => f.id !== info.id && f.id !== info.replaces)]);
      } else {
        const { line } = added;
        setProblems((list) => [...list, { name: file.name, line }]);
      }
    }
    setAdding(false);
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!id || !q) return;
    turn.current?.abort();
    const mine = new AbortController();
    turn.current = mine;
    setSearching(true);
    const response = await api(`/projects/${id}/search?q=${encodeURIComponent(q)}&k=${ASKED}`).catch(
      () => undefined,
    );
    setSearching(false);
    if (mine.signal.aborted) return; // the panel closed or another project opened meanwhile
    if (!response?.ok) {
      setFound({ state: "failed", line: await coreLine(response, texts.searchFailed) });
      return;
    }
    const body = (await response.json()) as { note: Text | null; results: Hit[]; rerank?: boolean };
    const chunkIds = body.results.flatMap((hit) => (hit.chunk_id === undefined ? [] : [hit.chunk_id]));
    const reordering = body.rerank === true && chunkIds.length > 1;
    setFound({ state: "found", note: body.note, results: body.results.slice(0, SHOWN), reordering });
    if (reordering) await rerank(id, q, chunkIds, mine.signal);
  }

  // The second step. On any failure, a 409 included, the first list stays and no error is shown.
  async function rerank(projectId: string, q: string, chunkIds: number[], signal: AbortSignal) {
    const response = await api(`/projects/${projectId}/rerank`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ q, chunk_ids: chunkIds }),
      signal,
    }).catch(() => undefined);
    const body = response?.ok
      ? ((await response.json().catch(() => undefined)) as { results: Hit[] } | undefined)
      : undefined;
    if (signal.aborted) return;
    setFound((now) =>
      now?.state === "found"
        ? { ...now, results: body ? body.results.slice(0, SHOWN) : now.results, reordering: false }
        : now,
    );
  }

  return (
    <section
      aria-labelledby={title}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault(); // the window must not open the file itself
        void add(Array.from(event.dataTransfer.files));
      }}
      className="border-b border-stone px-4 py-4"
    >
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <h2 id={title} className="font-semibold">
            {t("records")}
          </h2>
          <button type="button" onClick={onClose} className="text-slate hover:text-ink">
            {t("close")}
          </button>
        </div>

        {!project ? (
          <div className="flex items-center gap-3">
            <p>{t("pickProjectFirst")}</p>
            <button type="button" onClick={onPickProject} className="rounded-md border border-ink px-4 py-2">
              {t("projects")}
            </button>
          </div>
        ) : (
          <>
            <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-slate px-4 py-5 text-center">
              <p className="text-slate">{t("dropHere")}</p>
              <button
                type="button"
                disabled={adding}
                onClick={() => chooser.current?.click()}
                className="rounded-md border border-ink px-4 py-2 disabled:opacity-40"
              >
                {t("addFiles")}
              </button>
              <input
                ref={chooser}
                type="file"
                multiple
                hidden
                tabIndex={-1}
                onChange={(event) => {
                  const chosen = Array.from(event.target.files ?? []);
                  event.target.value = ""; // the same file can be chosen again
                  void add(chosen);
                }}
              />
              {adding && (
                <p role="status" className="text-slate">
                  {t("adding")}
                </p>
              )}
            </div>

            <MeaningStatus projectId={project.id} />

            {problems.length > 0 && (
              <div role="alert" className="flex flex-col gap-1 text-copper">
                {problems.map((problem, index) => (
                  <p key={index}>
                    <span dir="auto" className="font-semibold">
                      {problem.name}
                    </span>{" "}
                    {pick(problem.line)}
                  </p>
                ))}
              </div>
            )}

            {filesFailed && (
              <p role="alert" className="text-copper">
                {pick(filesFailed)}
              </p>
            )}
            {files?.length === 0 && <p className="text-slate">{t("noFiles")}</p>}
            {files && files.length > 0 && (
              <ul className="flex flex-col divide-y divide-stone">
                {files.map((file) => (
                  <li key={file.id} className="flex flex-col py-2">
                    <div className="flex items-center justify-between gap-4">
                      <FileName name={file.name} className="break-all" />
                      <span className={file.status === "read" ? "text-slate" : "text-copper"}>
                        {pick(statusText[file.status])}
                      </span>
                    </div>
                    {file.note && <p className="text-slate">{pick(file.note)}</p>}
                    {file.duplicate && <p className="text-slate">{t("fileDuplicate")}</p>}
                    {(file.flags ?? 0) > 0 && <HiddenText projectId={project.id} fileId={file.id} />}
                  </li>
                ))}
              </ul>
            )}

            <form onSubmit={search} role="search" className="flex items-end gap-2 border-t border-stone pt-3">
              <input
                type="search"
                aria-label={t("search")}
                placeholder={t("search")}
                dir="auto"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="flex-1 rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink"
              />
              <button
                type="submit"
                disabled={!query.trim() || searching}
                className="rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40"
              >
                {t("search")}
              </button>
            </form>

            {found?.state === "failed" && (
              <p role="alert" className="text-copper">
                {pick(found.line)}
              </p>
            )}
            {found?.state === "found" && (
              <div className="flex flex-col gap-2">
                {found.note && <p className="text-slate">{pick(found.note)}</p>}
                {found.reordering && (
                  <p role="status" className="text-slate">
                    {t("reordering")}
                  </p>
                )}
                {found.results.length === 0 && <p>{t("noResults")}</p>}
                <ol className="flex flex-col gap-2">
                  {found.results.map((hit, index) => (
                    <li key={index} className="rounded-md bg-stone px-3 py-2">
                      <div className="flex flex-wrap items-baseline gap-x-3 text-slate">
                        <FileName name={hit.file_name} className="font-semibold text-ink" />
                        <span>{where(hit.locator)}</span>
                      </div>
                      <p dir="auto" className="whitespace-pre-wrap">
                        {hit.text}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
