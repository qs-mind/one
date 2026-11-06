// Project Records for the open project: drop or add files, see what One could read in each, and search them.
// Files go to the core one at a time as their raw bytes; the page never sends a file path.
import { type FormEvent, type ReactNode, useContext, useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import { fill, language, pick, t, type Text, texts, useLanguage } from "../i18n";
import type { FileInfo } from "../project/types";
import { coreLine } from "../core";
import { MeaningStatus } from "./MeaningStatus";
import { useProject } from "./project";
import { FileName } from "../ui/FileName";
import { workspaceApi } from "../workspace/api";
import { DocumentsContext, startUpload } from "../workspace/documents";
import { chooseFolder } from "../import/FolderDrop";
import { importInto, reportDrop } from "../import/importer";
import { holdsFolder } from "../import/walk";

type Hit = {
  file_id: string;
  file_name: string;
  locator: Record<string, string | number>;
  text: string;
};
type Found = { state: "found"; note: Text | null; results: Hit[] } | { state: "failed"; line: Text };

// Search shows the core's top 10: words and meaning fused (no reranker since 5 Nov 2026). The box sends the
// query as typed; the core has no translation of its own, so the other language is found by meaning only.
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

// Hidden sheets, rows and columns are normal in a priced BOQ (its build-up): said plainly, never as a warning.
const LAYOUT = new Set(["hidden_sheet", "hidden_rows", "hidden_columns"]);

/** What a flagged file's mark says: orders to an AI (copper, with why ONE treats them as data), hidden sheets or rows
 * only (normal in priced BOQs), or text not shown on the page. */
function hiddenKind(kinds: readonly string[] | undefined): "orders" | "layout" | "unseen" {
  if (!kinds?.length || kinds.includes("ai_instruction")) return "orders";
  return kinds.every((kind) => LAYOUT.has(kind)) ? "layout" : "unseen";
}

/** The hidden-text mark on a flagged file; pressing it lists the flags, read from the core the first time. Copper,
 * with the prompt-injection words, only when a line looks like an order to an AI. */
function HiddenText({ projectId, fileId, kinds }: { projectId: string; fileId: string; kinds?: readonly string[] }) {
  const kind = hiddenKind(kinds);
  const warn = kind === "orders";
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
        className={`flex items-center gap-1 self-start underline-offset-2 hover:underline ${warn ? "text-copper" : "text-slate"}`}
      >
        {warn && warningIcon}
        {t(warn ? "hiddenText" : kind === "layout" ? "hiddenLayout" : "hiddenUnseen")}
      </button>
      {open && (
        <div className={`flex flex-col gap-1 rounded-md border px-3 py-2 ${warn ? "border-copper" : "border-stone"}`}>
          <p>{t(warn ? "hiddenTextWhy" : "hiddenNoOrders")}</p>
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

// Files dropped on the open document (any document of the workspace): they go to Project Records here, where Project
// files shows them arrive with what ONE read and any refusal.
let dropped: File[] = [];
const takers = new Set<() => void>();

/** Files dropped on the workspace, for Project files to add (it opens for them). */
export function addToRecords(files: File[]) {
  dropped.push(...files);
  for (const take of [...takers]) take();
}

/** An empty project's Project files: one thing, a drop area centred in the document and set high (its middle about a
 * third down), that asks for the tender files and says what ONE does with them. One step to press, Choose files, and a
 * quieter way to bring the whole tender folder (the folder chooser, import/FolderDrop.tsx; it goes into this project).
 * Dropping anywhere on the document works as on the list. No search, no meaning line, no "no files" words. */
function EmptyFiles({ adding, onChoose, problems, children }: { adding: boolean; onChoose(): void; problems: ReactNode; children: ReactNode }) {
  return (
    <div className="grid h-full grid-rows-[1fr_auto_2fr] justify-items-center px-3">
      <div
        data-empty-drop
        className="row-start-2 flex w-full max-w-xl flex-col items-center gap-2 rounded-[14px] border border-dashed border-slate bg-paper px-8 py-10 text-center"
      >
        <h2 className="text-lg font-semibold text-ink">{t("emptyFilesTitle")}</h2>
        <p className="max-w-md text-slate">{t("emptyFilesWhat")}</p>
        <div className="mt-3 flex flex-col items-center gap-2">
          <button
            type="button"
            disabled={adding}
            onClick={onChoose}
            className="h-8 rounded-md bg-ink px-4 text-paper hover:bg-ink/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            {t("chooseFiles")}
          </button>
          <button
            type="button"
            disabled={adding}
            onClick={() => chooseFolder(false)}
            className="rounded-md px-2 py-0.5 text-slate underline-offset-2 hover:text-ink hover:underline focus-visible:outline-2 focus-visible:outline-ink"
          >
            {t("orTenderFolder")}
          </button>
        </div>
        {children}
        {adding && (
          <p role="status" className="text-slate">
            {t("adding")}
          </p>
        )}
        {problems}
      </div>
    </div>
  );
}

/** `layout="document"`: Project files as the workspace's open document, with no panel chrome (the workspace names
 * it); a file opens there. */
type RecordsPanelProps =
  | { layout?: "panel"; onClose: () => void; onPickProject: () => void }
  | { layout: "document"; onClose?: undefined; onPickProject?: () => void };

export function RecordsPanel({ layout = "panel", onClose, onPickProject }: RecordsPanelProps) {
  useLanguage();
  const asDocument = layout === "document";
  const title = useId();
  const project = useProject();
  const chooser = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<RecordsFile[]>();
  const [filesFailed, setFilesFailed] = useState<Text>();
  const [adding, setAdding] = useState(false);
  // a refusal (copper), or a quiet line: the same file dropped under another name (slate)
  const [problems, setProblems] = useState<{ name: string; line: Text; quiet?: boolean }[]>([]);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [found, setFound] = useState<Found>();
  const turn = useRef<AbortController>(undefined); // the latest search; a newer one, or leaving, drops its answer
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

  // files that came another way (a tender folder chosen or dropped, an agent's), as the live events list them: the
  // list shows them too, so an empty project's drop area gives way to the list once its first file lands
  const known = useContext(DocumentsContext)?.files;
  useEffect(() => {
    if (!asDocument || !known || files === undefined) return;
    const missing = known.filter((k) => !files.some((f) => f.id === k.id || f.replaces === k.id));
    if (missing.length) setFiles([...missing, ...files.filter((f) => !missing.some((m) => m.replaces === f.id))]);
  }, [asDocument, known, files]);

  async function add(chosen: File[]) {
    if (!id || chosen.length === 0) return;
    setAdding(true);
    const ended = startUpload(); // the chat stops asking for the files at once
    setProblems([]);
    const landed: string[] = [];
    for (const file of chosen) {
      const added = await uploadFile(id, file);
      if (added.ok && added.info.duplicate && added.info.same_as) {
        // the same bytes under another name (or again): one line on the name dropped; the list keeps the one kept
        const line = added.info.same_as;
        setProblems((list) => [...list, { name: file.name, line, quiet: true }]);
      } else if (added.ok) {
        const { info } = added;
        landed.push(info.id);
        // the newest first; a new version takes the place of the one it replaces
        setFiles((list = []) => [info, ...list.filter((f) => f.id !== info.id && f.id !== info.replaces)]);
      } else {
        const { line } = added;
        setProblems((list) => [...list, { name: file.name, line }]);
      }
    }
    setAdding(false);
    ended();
    await reportDrop(id, landed); // one report in the project chat for the whole drop
  }

  // as the open document, it adds the files dropped on the workspace, once its own list is read
  const listed = files !== undefined || filesFailed !== undefined;
  const addRef = useRef(add);
  addRef.current = add;
  useEffect(() => {
    if (!asDocument || !id || !listed) return;
    const take = () => {
      const now = dropped;
      dropped = [];
      if (now.length) void addRef.current(now);
    };
    takers.add(take);
    take();
    return () => void takers.delete(take);
  }, [asDocument, id, listed]);

  async function search(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!id || !q) return;
    turn.current?.abort();
    const mine = new AbortController();
    turn.current = mine;
    setSearching(true);
    const response = await api(`/projects/${id}/search?q=${encodeURIComponent(q)}&k=${SHOWN}`).catch(
      () => undefined,
    );
    setSearching(false);
    if (mine.signal.aborted) return; // the panel closed or another project opened meanwhile
    if (!response?.ok) {
      setFound({ state: "failed", line: await coreLine(response, texts.searchFailed) });
      return;
    }
    const body = (await response.json()) as { note: Text | null; results: Hit[] };
    setFound({ state: "found", note: body.note, results: body.results.slice(0, SHOWN) });
  }

  const fileInput = (
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
  );
  const lines = (quiet: boolean) =>
    problems
      .filter((problem) => !!problem.quiet === quiet)
      .map((problem, index) => (
        <p key={index}>
          <span dir="auto" className="font-semibold">
            {problem.name}
          </span>{" "}
          {pick(problem.line)}
        </p>
      ));
  const problemLines = problems.length > 0 && (
    <>
      {problems.some((problem) => !problem.quiet) && (
        <div role="alert" className="flex flex-col gap-1 text-copper">
          {lines(false)}
        </div>
      )}
      {problems.some((problem) => problem.quiet) && (
        <div role="status" className="flex flex-col gap-1 text-slate">
          {lines(true)}
        </div>
      )}
    </>
  );
  // as the open document, nothing until the list is read (never the empty look for a moment), then one drop area
  // while the project has no file
  const reading = asDocument && !!project && files === undefined && !filesFailed;
  const empty = asDocument && !!project && files?.length === 0 && !filesFailed;

  return (
    <section
      aria-busy={reading || undefined}
      aria-labelledby={asDocument ? undefined : title}
      aria-label={asDocument ? t("projectFiles") : undefined}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault(); // the window must not open the file itself
        // a folder (a tender's): its files go into this project with their folders, as on the workspace
        if (id && holdsFolder(event.dataTransfer.items)) return void importInto(id, event.dataTransfer);
        void add(Array.from(event.dataTransfer.files));
      }}
      className={asDocument ? "h-full overflow-auto bg-paper p-3 text-ink" : "border-b border-stone px-4 py-4"}
    >
      <div className={empty ? "h-full" : asDocument ? "flex flex-col gap-3" : "mx-auto flex max-w-2xl flex-col gap-3"}>
        {!asDocument && (
          <div className="flex items-center justify-between gap-4">
            <h2 id={title} className="font-semibold">
              {t("records")}
            </h2>
            <button type="button" onClick={onClose} className="text-slate hover:text-ink">
              {t("close")}
            </button>
          </div>
        )}

        {!project ? (
          <div className="flex items-center gap-3">
            <p>{t("pickProjectFirst")}</p>
            {onPickProject && (
              <button type="button" onClick={onPickProject} className="rounded-md border border-ink px-4 py-2">
                {t("projects")}
              </button>
            )}
          </div>
        ) : reading ? null : empty ? (
          <EmptyFiles adding={adding} onChoose={() => chooser.current?.click()} problems={problemLines}>
            {fileInput}
          </EmptyFiles>
        ) : (
          <>
            {/* as the open document, one line: the room is the files' (dense, 5 Nov) */}
            <div
              className={`rounded-md border border-dashed border-slate ${
                asDocument ? "flex items-center justify-between gap-3 px-3 py-1.5" : "flex flex-col items-center gap-2 px-4 py-5 text-center"
              }`}
            >
              <p className="text-slate">{t("dropHere")}</p>
              <button
                type="button"
                disabled={adding}
                onClick={() => chooser.current?.click()}
                className={`rounded-md border border-ink disabled:opacity-40 ${asDocument ? "h-8 shrink-0 px-3" : "px-4 py-2"}`}
              >
                {t("addFiles")}
              </button>
              {fileInput}
              {adding && (
                <p role="status" className="text-slate">
                  {t("adding")}
                </p>
              )}
            </div>

            <MeaningStatus projectId={project.id} files={files?.length ?? 0} />

            {problemLines}

            {filesFailed && (
              <p role="alert" className="text-copper">
                {pick(filesFailed)}
              </p>
            )}
            {files?.length === 0 && <p className="text-slate">{t("noFiles")}</p>}
            {files && files.length > 0 && (
              <ul className="flex flex-col divide-y divide-stone">
                {files.map((file) => {
                  // in a button (the document), only phrasing elements
                  const Line = asDocument ? "span" : "div";
                  const Note = asDocument ? "span" : "p";
                  const line = (
                    <>
                      <Line className={`flex items-center justify-between gap-4${asDocument ? " w-full" : ""}`}>
                        <FileName name={file.name} fit />
                        <span className={`shrink-0 ${file.status === "read" ? "text-slate" : "text-copper"}`}>
                          {pick(statusText[file.status])}
                        </span>
                      </Line>
                      {file.note && <Note className="text-slate">{pick(file.note)}</Note>}
                      {file.duplicate && <Note className="text-slate">{t("fileDuplicate")}</Note>}
                    </>
                  );
                  return (
                    <li key={file.id} className="flex flex-col py-2">
                      {asDocument ? (
                        // the file opens as the workspace's document
                        <button
                          type="button"
                          onClick={() => workspaceApi.open(`file:${file.id}`)}
                          className="flex w-full flex-col items-start rounded-[10px] text-start hover:bg-stone/60 focus-visible:outline-2 focus-visible:outline-ink"
                        >
                          {line}
                        </button>
                      ) : (
                        line
                      )}
                      {(file.flags ?? 0) > 0 && <HiddenText projectId={project.id} fileId={file.id} kinds={file.flag_kinds} />}
                    </li>
                  );
                })}
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
                {found.results.length === 0 && <p>{t("noResults")}</p>}
                <ol className="flex flex-col gap-2">
                  {found.results.map((hit, index) => (
                    <li key={index} className="rounded-md bg-stone px-3 py-2">
                      <div className="flex flex-wrap items-baseline gap-x-3 text-slate">
                        <FileName name={hit.file_name} fit className="font-semibold text-ink" />
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
