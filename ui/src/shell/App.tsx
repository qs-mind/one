// The screen. With a project open: the top bar, and under it one document at the inline start (right in Arabic) and
// the project chat beside it at the inline end, both on the Stone ground; the command bar is at the chat's foot. With
// none: the General chat. One chat per chat id (the project's id, or "general"); switching project switches the chat
// and restores that project's open document. The screen saves nothing in the browser: the core keeps the chats with
// their Briefs, and the project's open document in the project's own file (workspace/documents.tsx).
import { DirectionProvider } from "@radix-ui/react-direction";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { sampleSources } from "../project/fake";
import { isMod, isTyping, matches } from "../project/keys";
import { leadFromChat, useWaiting } from "../project/live/activity";
import { Announcer } from "../project/live/Announcer";
import { currentSelection, select } from "../project/selection";
import { httpSources } from "../project/sources";
import type { ProjectSources, ProjectStatus } from "../project/types";
import { BackupPanel } from "../backup/BackupPanel";
import { Confidential } from "../backup/Confidential";
import { ProjectIndex } from "../deliverables/ProjectIndex";
import { FolderChooser, FolderDrop } from "../import/FolderDrop";
import { onBriefStarted } from "../import/importer";
import { CloseProject } from "../journey/CloseProject";
import { dir, useLanguage } from "../i18n";
import { restoreProject, useProject } from "../records/project";
import { leaveProject, openChat, ProjectPicker } from "../records/ProjectPicker";
import { RecordsPanel } from "../records/RecordsPanel";
import { AiSettings, useAiSettings } from "../settings/AiSettings";
import { Connectors } from "../settings/Connectors";
import { SearchKey } from "../settings/SearchKey";
import { useOpened, workspaceApi } from "../workspace/api";
import { DocumentsContext, useDocuments } from "../workspace/documents";
import { DocumentHead, Workspace } from "../workspace/Workspace";
import { CHAT_WIDTH, ChatPanel } from "./ChatPanel";
import { CommandBar } from "./CommandBar";
import { GENERAL, useActivity } from "./chatActivity";
import { onOpenPanel } from "./FixAction";
import { FloatingPanel } from "./FloatingPanel";
import { GeneralChat } from "./GeneralChat";
import { useNoticeCount } from "./Notices";
import { Palette } from "./Palette";
import { moveRegion, useNarrow, useSmall } from "./regions";
import { type PanelKind, TopBar } from "./TopBar";
import { showsWaitingCard, useChats } from "./useChats";

/** The dev-only sample mode (?sample=1): the screen shows sample data, labelled. Release builds drop it. */
function sampleMode(): boolean {
  return import.meta.env.DEV && new URLSearchParams(window.location.search).has("sample");
}

const projectSources = (projectId: string) => (sampleMode() ? sampleSources() : httpSources(projectId));

// the chat's width lasts for the session only (decision 4: nothing in web storage)
let sessionWidth = CHAT_WIDTH.start;

const STATUS_RELOAD_MS = 1000;
const WAITING_SYNC_MS = 1500;
const WAITING_FRAMES = 30;
const BRIEF_REREAD_MS = 2000; // after a screen starts a Brief, the chat checks it did not miss the Brief's end

export function App({ sourcesFor = projectSources }: { sourcesFor?: (projectId: string) => ProjectSources }) {
  useLanguage();
  const project = useProject();
  const narrow = useNarrow();
  const small = useSmall();
  const chat = useChats(project?.id ?? "general");
  const ai = useAiSettings();
  const sample = sampleMode();
  const sources = useMemo(() => (project ? sourcesFor(project.id) : undefined), [project?.id, sourcesFor, sample]);
  const documents = useDocuments(sources);
  // sample numbers are said once: in the open Deliverable's facts («الأرقام عينة»), else by the top bar
  const opened = useOpened();
  const factsSaySample =
    !!project && !!documents?.deliverables.some((d) => d.sample && opened?.key === `deliverable:${d.id}`);

  // AI settings in place of the chat: nothing connected yet, or the first AI just connected (it stays open to say so)
  const [aiMainOpen, setAiMainOpen] = useState(false);
  const [wasConnected, setWasConnected] = useState(ai.connected);
  if (wasConnected !== ai.connected) {
    // set while rendering, so the open settings are never unmounted in between
    setWasConnected(ai.connected);
    if (wasConnected === false && ai.connected) setAiMainOpen(true);
  }
  const aiMain = ai.connected === false || aiMainOpen;

  const [panel, setPanel] = useState<PanelKind | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [wideChat, setWideChat] = useState(true);
  const [sheetChat, setSheetChat] = useState(false);
  const chatShown = narrow ? sheetChat : wideChat || aiMain;
  const setChatShown = (shown: boolean) => (narrow ? setSheetChat(shown) : setWideChat(shown));
  const [width, setWidth] = useState(sessionWidth);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteOrigin, setPaletteOrigin] = useState<DOMRect>(); // the search field's place, when opened from it
  const [status, setStatus] = useState<ProjectStatus>({});
  const liveWaiting = useWaiting(); // the live stream's count, once it has said one; until then the status's
  const waiting = liveWaiting ?? status.waiting ?? 0;
  // "Waiting for you" counts every chat that waits: this project's cards, and each other chat waiting on the engineer
  const waitingElsewhere = useActivity().filter((c) => c.state === "waiting" && c.chat_id !== (project?.id ?? GENERAL));

  // The import reports and the backup question are cards at the chat's foot (Notices), never over the document: a
  // new one opens a folded chat, so it is seen.
  const notices = useNoticeCount();
  const noticesSeen = useRef(notices);
  useEffect(() => {
    if (notices > noticesSeen.current) setChatShown(true);
    noticesSeen.current = notices;
  }, [notices]);

  // A Brief started from a screen (the "I understood this" Brief, the lessons): the chat reads it from the core.
  // A short Brief may end between the chat's two reads (its messages, then its stream): when the chat is not
  // streaming a moment later, it reads the core once more, so it never shows as running a Brief that has ended.
  const chatStatus = useRef(chat.status);
  chatStatus.current = chat.status;
  useEffect(() => {
    let again: ReturnType<typeof setTimeout> | undefined;
    const off = onBriefStarted((projectId) => {
      if (projectId !== chat.chatId) return;
      setChatShown(true);
      void chat.resync();
      clearTimeout(again);
      again = setTimeout(() => {
        if (chatStatus.current !== "streaming" && chatStatus.current !== "submitted") void chat.resync();
      }, BRIEF_REREAD_MS);
    });
    return () => {
      off();
      clearTimeout(again);
    };
  }, [chat.chatId, chat.resync, narrow]);

  useEffect(() => {
    leadFromChat(chat.running); // before Plan 4 sends a Lead QS, the team shows the chat's own
  }, [chat.running]);

  // "Waiting for you" never points at a card the chat cannot show: when the core counts a waiting card that the
  // chat's messages lack for a moment, the chat is read again from the core (once per count).
  const synced = useRef<number>(0);
  const lacksCard = project !== undefined && waiting > 0 && !showsWaitingCard(chat.messages);
  useEffect(() => {
    if (waiting === 0) synced.current = 0;
    if (!lacksCard || synced.current === waiting) return;
    const timer = setTimeout(() => {
      synced.current = waiting;
      void chat.resync();
    }, WAITING_SYNC_MS);
    return () => clearTimeout(timer);
  }, [lacksCard, waiting, chat.resync]);

  useEffect(() => {
    // a remembered project that no longer opens is forgotten, and the projects show
    void restoreProject().then((result) => result === "failed" && setPanel("projects"));
  }, []);

  useEffect(() => {
    select([]); // a selection belongs to its project's document
  }, [project?.id]);

  useEffect(() => {
    // the project's status, read again when a Deliverable (the BOQ) moved
    setStatus({});
    if (!sources) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () =>
      void sources
        .status()
        .then((next) => {
          if (controller.signal.aborted) return;
          setStatus(next);
        })
        .catch(() => undefined); // the strip shows what it has
    const later = () => {
      clearTimeout(timer);
      timer = setTimeout(load, STATUS_RELOAD_MS);
    };
    load();
    sources.activity(
      (event) => {
        if (event.type === "deliverable") later();
      },
      controller.signal,
      load,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [sources]);

  // closed by a click outside it: focus stays where the engineer clicked
  const closePanel = useCallback((how?: unknown) => {
    setPanel(null);
    if (how !== "outside") opener.current?.focus();
  }, []);

  function togglePanel(kind: PanelKind, from: HTMLElement | null) {
    if (kind === "ai" && aiMain) return setChatShown(true); // the settings are already where the chat is
    if (panel === kind) return closePanel();
    opener.current = from;
    setPanel(kind);
  }

  /** The message box has no model to pick: the AI settings open, to connect one. */
  const connectAi = (from: HTMLElement) => togglePanel("ai", from);

  // A text away from its fix (the chat's "Open AI settings", a card's, the archive's "Open Backup") opens the panel,
  // as the More menu does; it stays open if it already is. Focus goes back to the button pressed when it closes.
  const showPanel = useRef<(kind: "ai" | "backup") => void>(undefined);
  showPanel.current = (kind) => {
    if (kind === "ai" && aiMain) return setChatShown(true); // the settings are already where the chat is
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setPanel(kind);
  };
  useEffect(() => onOpenPanel((kind) => showPanel.current?.(kind)), []);

  const projectsButton = () => document.querySelector<HTMLElement>('[data-region="topbar"] [data-region-start]');

  /** "Waiting for you": the chat opens at the first waiting card, scrolled to it, its first button focused. The chat
   * may still be opening, or reading the card from the core: a few frames are given for it to show. */
  function showWaiting() {
    setChatShown(true);
    let frames = WAITING_FRAMES;
    const go = () => {
      const card = document.querySelector<HTMLElement>("[data-waiting]");
      if (!card) return void (frames-- > 0 && requestAnimationFrame(go));
      card.scrollIntoView?.({ block: "center" });
      card.querySelector<HTMLElement>("button, input, textarea, select")?.focus({ preventScroll: true });
    };
    requestAnimationFrame(go);
  }

  /** A Deliverable's card (or the Close Project screen): it opens as the document; the narrow panel gives way. */
  function openDeliverable(id: string) {
    if (narrow) setSheetChat(false);
    workspaceApi.open(`deliverable:${id}`);
  }

  const openChatRef = useRef(() => setChatShown(true));
  openChatRef.current = () => setChatShown(true);
  // full screen: the chat folds and the document takes the width; the second press brings the chat back
  const toggleFullScreen = useRef(() => setChatShown(!chatShown));
  toggleFullScreen.current = () => setChatShown(!chatShown);
  useEffect(() => {
    // shortcuts by KeyboardEvent.code, so they work with the Arabic layout too (decision 10)
    function onKey(event: KeyboardEvent) {
      if (isMod(event) && matches(event, "KeyK")) {
        event.preventDefault();
        setPaletteOrigin(undefined);
        setPaletteOpen((open) => !open);
      } else if (isMod(event) && event.shiftKey && !event.altKey && event.code === "KeyF" && !isTyping(event.target)) {
        if (!document.querySelector("[data-region='document']")) return;
        event.preventDefault();
        toggleFullScreen.current();
      } else if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        currentSelection().length > 0 &&
        !document.querySelector("[role='dialog'], [role='alertdialog']")
      ) {
        select([]); // an Escape nothing else used: the selection the next message would go with is let go
      } else if (event.code === "F6") {
        event.preventDefault();
        moveRegion(event.shiftKey);
      } else if (event.code === "Slash" && !event.shiftKey && !event.altKey && !isMod(event) && !isTyping(event.target)) {
        if (document.querySelector("[role='dialog']")) return;
        const box = document.querySelector<HTMLElement>("[data-command-box]");
        if (box) {
          event.preventDefault();
          return box.focus();
        }
        if (!document.querySelector("[data-region='document']")) return;
        // the message box is in the chat only: a folded chat opens, to write there
        event.preventDefault();
        openChatRef.current();
        let frames = WAITING_FRAMES;
        const go = () => {
          const opened = document.querySelector<HTMLElement>("[data-command-box]");
          if (opened) opened.focus();
          else if (frames-- > 0) requestAnimationFrame(go);
        };
        requestAnimationFrame(go);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const body = {
    chat,
    ai,
    aiMain,
    onAiClose: () => setAiMainOpen(false),
  };

  const floatingPanel = panel && (
    <FloatingPanel onClose={closePanel} wide={panel === "deliverables"} narrow={panel === "projects"}>
      {panel === "ai" && (
        <>
          <AiSettings ai={ai} onClose={closePanel} />
          <SearchKey />
          <Connectors />
        </>
      )}
      {panel === "projects" && <ProjectPicker onClose={closePanel} />}
      {panel === "records" && project && (
        <RecordsPanel onClose={closePanel} onPickProject={() => setPanel("projects")} />
      )}
      {panel === "deliverables" && project && (
        <ProjectIndex
          projectId={project.id}
          onOpen={(id) => {
            // the index closes, so it never sits over the document it opened
            setPanel(null);
            openDeliverable(id);
          }}
          onClose={closePanel}
        />
      )}
      {panel === "backup" && <BackupPanel onClose={closePanel} />}
      {panel === "close" && project && (
        <CloseProject project={project} briefRunning={chat.running} onOpenDeliverable={openDeliverable} onClose={closePanel} />
      )}
      {panel === "confidential" && project && <Confidential project={project} onClose={closePanel} />}
    </FloatingPanel>
  );

  return (
    <DirectionProvider dir={dir()}>
      <DocumentsContext.Provider value={documents}>
        <div className={`flex h-dvh flex-col text-ink ${project ? "bg-stone" : "bg-paper"}`}>
          <TopBar
            project={project}
            status={status}
            sources={sources}
            sample={sample && !factsSaySample}
            narrow={narrow}
            panel={panel}
            onPanel={togglePanel}
            aiExpanded={panel === "ai" || aiMain}
            waiting={waiting + waitingElsewhere.length}
            onWaiting={() => (waiting > 0 || !waitingElsewhere[0] ? showWaiting() : void openChat(waitingElsewhere[0].chat_id))}
            onPalette={(origin) => {
              setPaletteOrigin(origin);
              setPaletteOpen(true);
            }}
            chatOpen={chatShown}
            onChat={() => setChatShown(!chatShown)}
            document={project && documents && <DocumentHead documents={documents} />}
            fullScreen={!chatShown}
            onFullScreen={() => toggleFullScreen.current()}
          />
          <div className="relative flex min-h-0 flex-1 flex-col">
            {project && sources ? (
              // dense (5 Nov): the room is the data's: 8 px under the top bar and above the window's foot, 12 px at
              // the sides and between the document and the chat
              // below 640 px the document loses its side gutters: the phone's width is all the data's
              <main
                className={`relative flex min-h-0 flex-1 gap-3 py-2 ${small ? "px-0" : "px-3"}`}
                // files dropped beside the document (the chat, the gutters) are taken by nothing: the window must
                // not open them in its place (dragDropEnabled is off, so the webview's own drop is the page's)
                onDragOver={(event) => event.dataTransfer.types.includes("Files") && event.preventDefault()}
                onDrop={(event) => event.dataTransfer.types.includes("Files") && event.preventDefault()}
              >
                {documents ? (
                  <Workspace projectId={project.id} sources={sources} documents={documents} />
                ) : (
                  <div className="min-w-0 flex-1" aria-busy="true" />
                )}
                <ChatPanel
                  {...body}
                  composer={ai.connected !== false && <CommandBar chat={chat} ai={ai} onConnectAi={connectAi} inPanel />}
                  projectId={project.id}
                  onOpenDeliverable={openDeliverable}
                  open={chatShown}
                  onOpen={() => setChatShown(true)}
                  onClose={() => setChatShown(false)}
                  narrow={narrow}
                  small={small}
                  waiting={waiting + waitingElsewhere.length > 0}
                  width={width}
                  onWidth={(next) => {
                    sessionWidth = next;
                    setWidth(next);
                  }}
                />
                {floatingPanel}
              </main>
            ) : (
              <>
                <FolderDrop className="flex min-h-0 flex-1 flex-col">
                  <GeneralChat {...body} onConnectAi={connectAi} />
                </FolderDrop>
                {floatingPanel}
              </>
            )}
            <FolderChooser />
          </div>
          <Palette
            open={paletteOpen}
            origin={paletteOrigin}
            onOpenChange={setPaletteOpen}
            project={project}
            documents={documents}
            chatOpen={chatShown}
            onToggleChat={() => setChatShown(!chatShown)}
            onGeneralChat={leaveProject}
            onNewProject={() => {
              opener.current = projectsButton();
              setPanel("projects");
            }}
            onPanel={(kind) => {
              if (kind === "ai" && aiMain) return setChatShown(true); // the settings are already where the chat is
              opener.current = document.querySelector<HTMLElement>("[data-search-field]") ?? projectsButton();
              setPanel(kind);
            }}
          />
          <Announcer />
        </div>
      </DocumentsContext.Provider>
    </DirectionProvider>
  );
}
