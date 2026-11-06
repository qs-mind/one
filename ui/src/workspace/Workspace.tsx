// The document area: the open document in a Paper sheet on the Stone ground (radius 10, a 1 px Slate 18 % ring), from
// 8 px under the top bar to 8 px from the window's foot, with the thin line by the row an agent works on over it; its
// title and switcher are in the top bar (DocumentHead). Alt and the arrow that points back (→ in Arabic, ← in English) go Back, to the same row. A newly shown document fades in
// over 200 ms (at once with reduced motion). A selection in the document is the composer's chip; a source opened
// from its card is marked in the file, or said once when its place cannot be.
import { useEffect, useLayoutEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { dir, t, useLanguage } from "../i18n";
import { isMod, isTyping } from "../project/keys";
import { useAgents, type LiveAgent } from "../project/live/activity";
import { select } from "../project/selection";
import type { Anchor, DocKey, Opened, ProjectSources, ViewerHandle } from "../project/types";
import { importInto } from "../import/importer";
import { holdsFolder } from "../import/walk";
import { addToRecords } from "../records/RecordsPanel";
import { revealSource, REVEAL_WAIT_MS } from "../sources/mark";
import { play } from "../ui/motion";
import { useOpened, workspaceApi } from "./api";
import { DocumentSwitcher } from "./DocumentSwitcher";
import { DocumentView } from "./DocumentView";
import { titleOf, type Documents } from "./documents";
import { markFor } from "./reveal";
import { LiveWorkingLine } from "./WorkingLine";

const FADE_MS = 200;
const DOC_KINDS = ["deliverable:", "file:", "clientboq:", "files:"];
const isDocKey = (key: string): key is DocKey => DOC_KINDS.some((kind) => key.startsWith(kind));

const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

/** Back: Alt with the arrow that points back in the page's direction; never while writing (it moves by word there). */
function useBackKeys() {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!event.altKey || event.shiftKey || isMod(event) || event.defaultPrevented || isTyping(event.target)) return;
      if (event.code !== (dir() === "rtl" ? "ArrowRight" : "ArrowLeft")) return;
      if (workspaceApi.back()) event.preventDefault();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}

/** Shows `anchor`'s row once the viewer has it (it loads its own data): Back and a restore come back to the row. */
function useRowShown(opened: Opened, handle: ViewerHandle | null) {
  useEffect(() => {
    const anchor = opened.anchor;
    if (!handle || !anchor?.row || !opened.key.startsWith("deliverable:")) return;
    let live = true;
    void (async () => {
      const started = Date.now();
      while (live && !handle.locate(anchor) && Date.now() - started < REVEAL_WAIT_MS) await nextFrame();
    })();
    return () => {
      live = false;
    };
  }, [opened, handle]); // each opening once: a selection moving the anchor in place scrolls nothing
}

/** Marks the source this opening came from, once it shows; `unmarked` when its place cannot be marked. */
function useSourceMark(opened: Opened): boolean {
  const [unmarked, setUnmarked] = useState<Opened | null>(null);
  useEffect(() => {
    const mark = markFor(opened);
    if (!mark) return;
    let live = true;
    void revealSource(mark.keys, mark.figures).then((marked) => live && !marked && setUnmarked(opened));
    return () => {
      live = false;
    };
  }, [opened]);
  return unmarked === opened;
}

const carriesFiles = (event: DragEvent) => event.dataTransfer?.types?.includes("Files") ?? false;

/** Files or a folder dropped anywhere on the document: a folder (a tender's) goes into the project with its folders,
 * files go to Project Records (Project files opens to show them come). Taken on the way down (capture), before a
 * viewer under the pointer (a letter's editor) can take the drop as its own; Project files takes its own drops. */
function dropHandlers(projectId: string, opened: Opened) {
  const ours = (event: DragEvent) => carriesFiles(event) && opened.key !== "files:all";
  return {
    onDragOverCapture(event: DragEvent) {
      if (ours(event)) event.preventDefault();
    },
    onDropCapture(event: DragEvent) {
      if (!ours(event)) return;
      event.preventDefault();
      event.stopPropagation(); // the editor never inserts it
      if (holdsFolder(event.dataTransfer.items)) return void importInto(projectId, event.dataTransfer);
      const files = Array.from(event.dataTransfer.files);
      if (!files.length) return;
      workspaceApi.open("files:all"); // Back returns to the document
      addToRecords(files);
    },
  };
}

/** One document as shown: it fades in as it comes (keyed by the document, so each one starts fresh). */
function Shown({ children }: { children: ReactNode }) {
  const sheet = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (sheet.current) void play(sheet.current, [{ opacity: 0 }, { opacity: 1 }], FADE_MS);
  }, []);
  return (
    <div ref={sheet} className="relative h-full">
      {children}
    </div>
  );
}

export function Workspace({ projectId, sources, documents }: { projectId: string; sources: ProjectSources; documents: Documents }) {
  useLanguage();
  const opened = useOpened();
  useBackKeys();
  if (!opened) return null;
  return <Open projectId={projectId} sources={sources} documents={documents} opened={opened} />;
}

/** The documents an agent is working on now, for the switcher's dots. */
function workingOn(agents: readonly LiveAgent[]): Set<DocKey> {
  return new Set(
    agents.flatMap((a) => ((a.state === "thinking" || a.state === "working") && a.focus && isDocKey(a.focus.frame) ? [a.focus.frame] : [])),
  );
}

/** The open document's title (its switcher) and state, for the top bar: the sheet keeps all the height below it. */
export function DocumentHead({ documents }: { documents: Documents }) {
  useLanguage();
  const opened = useOpened();
  const agents = useAgents();
  if (!opened) return null;
  return (
    <DocumentSwitcher
      deliverables={documents.deliverables}
      clientBoqs={documents.clientBoqs}
      files={documents.files}
      opened={opened}
      working={workingOn(agents)}
    />
  );
}

function Open({ projectId, sources, documents, opened }: { projectId: string; sources: ProjectSources; documents: Documents; opened: Opened }) {
  const [handle, setHandle] = useState<ViewerHandle | null>(null);
  const [box, setBox] = useState<HTMLElement | null>(null); // where the document scrolls: the first element that did
  const unmarked = useSourceMark(opened);
  useRowShown(opened, handle);

  // a selection belongs to its document: another document opening lets it go
  const shownKey = useRef(opened.key);
  useEffect(() => {
    if (shownKey.current !== opened.key) select([]);
    shownKey.current = opened.key;
  }, [opened.key]);

  const onSelection = (anchor: Anchor | null, label: string | null) => {
    const id = opened.key.slice(opened.key.indexOf(":") + 1);
    if (!anchor) return select([]);
    workspaceApi.at(anchor); // Back comes back here
    select([{ kind: "deliverable", id, title: titleOf(documents, opened.key) ?? "", anchor, ...(label ? { label } : {}) }]);
  };

  return (
    <section
      data-region="document"
      aria-label={titleOf(documents, opened.key) ?? t("projectFiles")}
      tabIndex={-1}
      className="flex min-h-0 min-w-0 flex-1 flex-col outline-none"
      {...dropHandlers(projectId, opened)}
    >
      <div data-document-sheet className="relative min-h-0 flex-1 overflow-hidden rounded-[10px] bg-paper ring-1 ring-slate/18">
        <Shown key={opened.key}>
          <div
            ref={setBox}
            className="relative h-full"
            onScrollCapture={(event) => {
              const scrolled = event.target;
              if (scrolled instanceof HTMLElement && scrolled !== box) setBox(scrolled);
            }}
          >
            {/* a source whose place cannot be shown is said in the file's own control row, never over its controls */}
            <DocumentView
              projectId={projectId}
              sources={sources}
              opened={opened}
              ref={setHandle}
              onSelection={onSelection}
              notice={unmarked ? t("sourceNotMarked") : null}
            />
            <LiveWorkingLine handle={handle} opened={opened.key} box={box} />
          </div>
        </Shown>
      </div>
    </section>
  );
}
