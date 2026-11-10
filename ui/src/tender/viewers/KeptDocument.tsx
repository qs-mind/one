// The kept document engines in the tender's document place: the old workspace's DocumentView (a Deliverable's sheet,
// document or pack viewer, a file's pages or text, the Project Map, Project files), unchanged, inside a thin frame.
// The route names the document (a DocKey: "deliverable:<id>", "file:<id>", "view:project-map", "files:all"); the
// engines open others through the old store (workspaceApi), and each such opening becomes the route. A sheet is dense
// (its rows as high as the dense scope's --sheet-row-h), and a number clicked in it shows its source in a panel under it.
import { type RefObject, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { paths } from "@/app/paths";
import { httpSources } from "@/project/sources";
import type { DocKey, ProjectSources } from "@/project/types";
import type { NumberAsked } from "@/viewers/sheet/numberTarget";
import { DenseRowHeight, NumberTarget } from "@/viewers/sheet/numberTarget";
import { subscribeOpened, useOpened, workspaceApi } from "@/workspace/api";
import { DocumentView } from "@/workspace/DocumentView";
import { type Documents, DocumentsContext, titleOf } from "@/workspace/documents";
import { useKeptLanguage } from "./keptLanguage";
import { SourcePanel } from "./SourcePanel";

const KINDS = ["files", "file", "deliverable", "clientboq", "view"] as const;

/** The route's document as a DocKey, or null when it names none the engines know. */
export function docKeyOf(docId: string): DocKey | null {
  const at = docId.indexOf(":");
  const kind = docId.slice(0, at);
  return at > 0 && at < docId.length - 1 && (KINDS as readonly string[]).includes(kind) ? (docId as DocKey) : null;
}

export type KeptDocuments = { sources: ProjectSources; docs: Documents | null };

/** The tender's documents, read once per tender once the core has opened it (`open`): the sources the engines read
 * through, and the lists they name. */
export function useKeptDocuments(projectId: string, open: boolean): KeptDocuments {
  const sources = useMemo(() => httpSources(projectId), [projectId]);
  const [docs, setDocs] = useState<Documents | null>(null);
  useEffect(() => {
    let live = true;
    setDocs(null);
    if (!open) return;
    void Promise.all([sources.deliverables().catch(() => null), sources.files().catch(() => null)]).then(([deliverables, files]) => {
      if (live) setDocs({ deliverables: deliverables ?? [], files: files ?? [], clientBoqs: [], desks: [], ...(files ? {} : { filesFailed: true }) });
    });
    return () => {
      live = false;
    };
  }, [sources, open]);
  return { sources, docs };
}

/** The document's name as the engines give it, or null while it is not known. */
export function keptTitle(docs: Documents | null, key: DocKey): string | null {
  return docs ? titleOf(docs, key) : null;
}

/** The design system's --sheet-row-h (2.25rem), for a page without tokens.css. */
const ROW_PX = 36;
const REM_PX = 16; // the engines' px are at 100 %

/** A one-line row's height from the scope's `--sheet-row-h`, in px at 100 %. */
function useRowHeight(scope: RefObject<HTMLElement | null>): number {
  const [px, setPx] = useState(ROW_PX);
  useLayoutEffect(() => {
    const value = scope.current ? getComputedStyle(scope.current).getPropertyValue("--sheet-row-h").trim() : "";
    const n = parseFloat(value);
    if (Number.isFinite(n) && n > 0) setPx(value.endsWith("rem") ? n * REM_PX : n);
  }, [scope]);
  return px;
}

export function KeptDocument({ projectId, docKey, sources, docs }: { projectId: string; docKey: DocKey } & KeptDocuments) {
  useKeptLanguage();
  const navigate = useNavigate();
  const opened = useOpened();
  const [asked, setAsked] = useState<NumberAsked | null>(null);
  const scope = useRef<HTMLDivElement>(null);
  const rowHeight = useRowHeight(scope);

  // The route leads: the store follows it, and an opening inside the engines moves the route.
  useEffect(() => {
    if (workspaceApi.current()?.key !== docKey) workspaceApi.open(docKey);
    setAsked(null);
  }, [docKey]);
  useEffect(
    () =>
      subscribeOpened(() => {
        const now = workspaceApi.current();
        if (now && now.key !== docKey) navigate(paths.doc(projectId, now.key));
      }),
    [docKey, projectId, navigate],
  );

  const shown = opened?.key === docKey ? opened : { key: docKey, anchor: null };
  return (
    <DocumentsContext.Provider value={docs}>
      <NumberTarget.Provider value={setAsked}>
        <DenseRowHeight.Provider value={rowHeight}>
          <div ref={scope} data-region="document" className="dense flex h-full min-h-0 flex-col gap-4 text-base">
            <div className="min-h-0 flex-1">
              <DocumentView projectId={projectId} sources={sources} opened={shown} />
            </div>
            {asked && <SourcePanel projectId={projectId} asked={asked} onClose={() => setAsked(null)} />}
          </div>
        </DenseRowHeight.Provider>
      </NumberTarget.Provider>
    </DocumentsContext.Provider>
  );
}
