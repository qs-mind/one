// Project Records for the open project: drop or add files, see what One could read in each, and search them.
// Files go to the core one at a time as their raw bytes; the page never sends a file path.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { fill, pick, t, type Text, texts, useLanguage } from "../i18n";
import type { FileInfo } from "../canvas/types";
import { coreLine } from "../core";
import { MeaningStatus } from "./MeaningStatus";
import { useProject } from "./project";

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

export function RecordsPanel({ onClose, onPickProject }: { onClose: () => void; onPickProject: () => void }) {
  useLanguage();
  const title = useId();
  const project = useProject();
  const chooser = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FileInfo[]>();
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
      const response = await fetch(`/api/projects/${id}/files`).catch(() => undefined);
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
      const response = await fetch(`/api/projects/${id}/files?name=${encodeURIComponent(file.name)}`, {
        method: "POST",
        body: file,
      }).catch(() => undefined);
      if (response?.ok) {
        const info = (await response.json()) as FileInfo;
        // the newest first; a new version takes the place of the one it replaces
        setFiles((list = []) => [info, ...list.filter((f) => f.id !== info.id && f.id !== info.replaces)]);
      } else {
        const line = await coreLine(response, texts.fileNotAdded);
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
    const response = await fetch(`/api/projects/${id}/search?q=${encodeURIComponent(q)}&k=${ASKED}`).catch(
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
    const response = await fetch(`/api/projects/${projectId}/rerank`, {
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
                      <span dir="auto" className="break-all">
                        {file.name}
                      </span>
                      <span className={file.status === "read" ? "text-slate" : "text-copper"}>
                        {pick(statusText[file.status])}
                      </span>
                    </div>
                    {file.note && <p className="text-slate">{pick(file.note)}</p>}
                    {file.duplicate && <p className="text-slate">{t("fileDuplicate")}</p>}
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
                        <span dir="auto" className="font-semibold text-ink">
                          {hit.file_name}
                        </span>
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
