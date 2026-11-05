// The screen. With a project open: the top bar, and under it the Project Canvas filling the window, with the
// project chat, the command bar and the zoom controls floating over it. With none: the General chat. One chat per
// chat id (the project's id, or "general"); switching project switches the chat. The screen saves nothing itself:
// the core keeps the chats with their Briefs, and the canvas keeps its layout in the project's own file.
import { DirectionProvider } from "@radix-ui/react-direction";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { canvasApi } from "../canvas/api";
import { Canvas } from "../canvas/Canvas";
import { CHAT_STARTS_OPEN, DELIVERABLE_CARD_OPENS } from "../canvas/choices";
import { sampleSources } from "../canvas/fake";
import { isMod, isTyping, matches } from "../canvas/keys";
import { leadFromChat, useWaiting } from "../canvas/live/activity";
import { Announcer } from "../canvas/live/Announcer";
import { Cursors } from "../canvas/live/Cursors";
import { select } from "../canvas/selection";
import { httpSources } from "../canvas/sources";
import type { FrameKey, ProjectSources, ProjectStatus } from "../canvas/types";
import { ProjectIndex } from "../deliverables/ProjectIndex";
import { dir, useLanguage } from "../i18n";
import { restoreProject, useProject } from "../records/project";
import { leaveProject, ProjectPicker } from "../records/ProjectPicker";
import { RecordsPanel } from "../records/RecordsPanel";
import { AiSettings, useAiSettings } from "../settings/AiSettings";
import { CHAT_WIDTH, ChatPanel } from "./ChatPanel";
import { CommandBar } from "./CommandBar";
import { DeliverablePanel, useDeliverablePanel } from "./DeliverablePanel";
import { FloatingPanel } from "./FloatingPanel";
import { GeneralChat } from "./GeneralChat";
import { Palette } from "./Palette";
import { moveRegion, useNarrow } from "./regions";
import { type PanelKind, TopBar } from "./TopBar";
import { useChats } from "./useChats";

/** The dev-only sample mode (?sample=1): the canvas shows sample data, labelled. Release builds drop it. */
function sampleMode(): boolean {
  return import.meta.env.DEV && new URLSearchParams(window.location.search).has("sample");
}

const projectSources = (projectId: string) => (sampleMode() ? sampleSources() : httpSources(projectId));

// the chat's width lasts for the session only (decision 4: nothing in web storage)
let sessionWidth = CHAT_WIDTH.start;

/** The zoom controls take the bottom inline start; the command bar sits between them and the chat. */
const ZOOM_SPACE = 272;
const STATUS_RELOAD_MS = 1000;

export function App({ sourcesFor = projectSources }: { sourcesFor?: (projectId: string) => ProjectSources }) {
  useLanguage();
  const project = useProject();
  const narrow = useNarrow();
  const chat = useChats(project?.id ?? "general");
  const ai = useAiSettings();
  const sample = sampleMode();
  const sources = useMemo(() => (project ? sourcesFor(project.id) : undefined), [project?.id, sourcesFor, sample]);

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
  const [wideChat, setWideChat] = useState(CHAT_STARTS_OPEN);
  const [sheetChat, setSheetChat] = useState(false);
  const chatShown = narrow ? sheetChat : wideChat || aiMain;
  const setChatShown = (shown: boolean) => (narrow ? setSheetChat(shown) : setWideChat(shown));
  const [width, setWidth] = useState(sessionWidth);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const deliverable = useDeliverablePanel(project?.id);
  const [status, setStatus] = useState<ProjectStatus>({});
  const liveWaiting = useWaiting(); // the live stream's count, once it has said one; until then the status's
  const waiting = liveWaiting ?? status.waiting ?? 0;

  useEffect(() => {
    leadFromChat(chat.running); // before Plan 4 sends a Lead QS, the team shows the chat's own
  }, [chat.running]);

  useEffect(() => {
    // a remembered project that no longer opens is forgotten, and the projects show
    void restoreProject().then((result) => result === "failed" && setPanel("projects"));
  }, []);

  useEffect(() => {
    select([]); // a selection belongs to its project's canvas
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

  const closePanel = useCallback(() => {
    setPanel(null);
    opener.current?.focus();
  }, []);

  function togglePanel(kind: PanelKind, from: HTMLElement | null) {
    if (kind === "ai" && aiMain) return setChatShown(true); // the settings are already where the chat is
    if (panel === kind) return closePanel();
    opener.current = from;
    setPanel(kind);
  }

  const projectsButton = () => document.querySelector<HTMLElement>('[data-region="topbar"] [data-region-start]');

  function showWaiting() {
    setChatShown(true);
    requestAnimationFrame(() => document.querySelector<HTMLElement>("[data-waiting] button")?.focus());
  }

  function openDeliverable(id: string) {
    const key: FrameKey = `deliverable:${id}`;
    if (DELIVERABLE_CARD_OPENS === "frame" && canvasApi.frames().some((frame) => frame.key === key)) {
      if (narrow) setSheetChat(false);
      canvasApi.focusFrame(key);
    } else {
      deliverable.show(id);
    }
  }

  useEffect(() => {
    // shortcuts by KeyboardEvent.code, so they work with the Arabic layout too (decision 10)
    function onKey(event: KeyboardEvent) {
      if (isMod(event) && matches(event, "KeyK")) {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      } else if (event.code === "F6") {
        event.preventDefault();
        moveRegion(event.shiftKey);
      } else if (event.code === "Slash" && !event.shiftKey && !event.altKey && !isMod(event) && !isTyping(event.target)) {
        const box = document.querySelector<HTMLElement>("[data-command-box]");
        if (!box || document.querySelector("[role='dialog']")) return;
        event.preventDefault();
        box.focus();
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
    <FloatingPanel onClose={closePanel}>
      {panel === "ai" && <AiSettings ai={ai} onClose={closePanel} />}
      {panel === "projects" && <ProjectPicker onClose={closePanel} />}
      {panel === "records" && project && (
        <RecordsPanel onClose={closePanel} onPickProject={() => setPanel("projects")} />
      )}
      {panel === "deliverables" && project && (
        <ProjectIndex projectId={project.id} onOpen={(id) => deliverable.show(id)} onClose={closePanel} />
      )}
    </FloatingPanel>
  );

  const fullScreen = deliverable.open !== null && deliverable.full;

  return (
    <DirectionProvider dir={dir()}>
      <div className="flex h-dvh flex-col bg-paper text-ink">
        <TopBar
          project={project}
          status={status}
          sources={sources}
          sample={sample}
          narrow={narrow}
          panel={panel}
          onPanel={togglePanel}
          aiExpanded={panel === "ai" || aiMain}
          waiting={waiting}
          onWaiting={showWaiting}
          onPalette={() => setPaletteOpen(true)}
          chatOpen={chatShown}
          onChat={() => setChatShown(!chatShown)}
        />
        <div className="relative flex min-h-0 flex-1 flex-col">
          {project && sources ? (
            <main className="relative min-h-0 flex-1 overflow-hidden">
              <div data-region="canvas" tabIndex={-1} className="absolute inset-0 outline-none" inert={fullScreen}>
                <Canvas projectId={project.id} sources={sources} onOpenFull={(id) => deliverable.show(id, true)}>
                  <Cursors />
                </Canvas>
              </div>
              <ChatPanel
                {...body}
                projectId={project.id}
                onOpenDeliverable={openDeliverable}
                open={chatShown}
                onOpen={() => setChatShown(true)}
                onClose={() => setChatShown(false)}
                narrow={narrow}
                width={width}
                onWidth={(next) => {
                  sessionWidth = next;
                  setWidth(next);
                }}
              />
              {ai.connected !== false && (
                <CommandBar
                  chat={chat}
                  onSent={() => setChatShown(true)}
                  floating={narrow ? { start: 8, end: 8, bottom: 64 } : { start: ZOOM_SPACE, end: chatShown ? width + 32 : 16, bottom: 16 }}
                />
              )}
              {floatingPanel}
              <DeliverablePanel panel={deliverable} projectId={project.id} onSend={(text) => void chat.send(text)} />
            </main>
          ) : (
            <>
              <GeneralChat {...body} />
              {floatingPanel}
            </>
          )}
        </div>
        <Palette
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          project={project}
          sources={sources}
          chatOpen={chatShown}
          onToggleChat={() => setChatShown(!chatShown)}
          onGeneralChat={leaveProject}
          onNewProject={() => {
            opener.current = projectsButton();
            setPanel("projects");
          }}
        />
        <Announcer />
      </div>
    </DirectionProvider>
  );
}
