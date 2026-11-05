// The top bar, 56 px: the mark, the project (or the General chat) with its switcher, the project's status (its two
// most important items; the rest in More status), the agent the view follows, who is working now, "Waiting for you",
// then the search field (it opens the palette from itself), the Deliverables and Project Records. AI settings and the other language are always in More: they are
// set once, not used every hour, and so is Setup, the first launch's steps again. Below 900 px the status folds into one Status button and the rest into More; below
// 1280 px search and the panels fold into More too: the project's name is never cut. The chrome mirrors in Arabic.
import { useRef } from "react";
import { Mark } from "../brand/Mark";
import type { ProjectSources, ProjectStatus } from "../canvas/types";
import { isMac } from "../canvas/keys";
import { Following, TeamNow } from "../canvas/live/TeamNow";
import { send } from "../core";
import { openSetup } from "../firstlaunch/parts";
import { chooseFolder } from "../import/FolderDrop";
import { fill, language, setLanguage, t, useLanguage } from "../i18n";
import type { Project } from "../records/project";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "../ui/popover";
import { centreOf, withTransition } from "../ui/viewTransition";
import { useCompact } from "./regions";
import { StatusStrip } from "./StatusStrip";

export type PanelKind = "ai" | "projects" | "records" | "deliverables" | "backup" | "close" | "confidential";

export { Mark }; // the first launch's header takes it from here

const button = "whitespace-nowrap rounded-lg px-3 py-1.5 hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink";

export type TopBarProps = {
  /** None: the General chat. */
  project: Project | undefined;
  status: ProjectStatus;
  sources?: ProjectSources;
  sample: boolean;
  narrow: boolean;
  panel: PanelKind | null;
  /** Opens or closes a panel; `opener` gets focus back when it closes. */
  onPanel(kind: PanelKind, opener: HTMLElement): void;
  aiExpanded: boolean;
  waiting: number;
  onWaiting(): void;
  /** Opens the palette; from `origin`, the search field's place, when it was clicked. */
  onPalette(origin?: DOMRect): void;
  /** Narrow layout: the chat sheet. */
  chatOpen: boolean;
  onChat(): void;
};

export function TopBar(props: TopBarProps) {
  const lang = useLanguage();
  const { project, narrow, panel, onPanel } = props;
  const more = useRef<HTMLButtonElement>(null);
  const keys = isMac() ? "⌘K" : "Ctrl K";
  const compact = useCompact(); // the tools fold into More before the project name or the status would be cut

  const search = (
    <button type="button" className={button} onClick={() => props.onPalette()}>
      {fill(t("searchKeys"), { keys })}
    </button>
  );
  // A field to look at, a button to use: the palette grows from it and closes back into it, and focus comes back here.
  const searchField = (
    <button
      type="button"
      data-search-field=""
      aria-label={fill(t("searchKeys"), { keys })}
      className="flex w-48 items-center justify-between gap-4 rounded-lg border border-ink/10 bg-stone/60 px-3 py-1.5 text-start whitespace-nowrap hover:border-ink/20 hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
      onClick={(event) => {
        event.currentTarget.focus(); // WebKit does not focus a clicked button; the palette gives focus back to this
        props.onPalette(event.currentTarget.getBoundingClientRect());
      }}
    >
      <span>{t("searchField")}</span>
      <kbd dir="ltr" className="font-sans text-xs text-slate">
        {keys}
      </kbd>
    </button>
  );
  const ai = (opener?: HTMLElement | null) => (
    <button
      type="button"
      aria-expanded={props.aiExpanded}
      className={button}
      onClick={(event) => onPanel("ai", opener ?? event.currentTarget)}
    >
      {t("ai")}
    </button>
  );
  const otherLanguage = (
    <button
      type="button"
      lang={lang === "ar" ? "en" : "ar"}
      className={button}
      onClick={(event) => {
        const next = language() === "ar" ? "en" : "ar";
        void withTransition(() => setLanguage(next), centreOf(event.currentTarget)); // the wipe spreads from here
        // the core starts some Briefs itself (a tender folder's, a project's lessons): in the language on the screen
        void send("/setup/language", "PUT", { state: "done", lang: next });
      }}
    >
      {t("otherLanguage")}
    </button>
  );
  const projectPanels = (opener?: HTMLElement | null) =>
    project && (
      <>
        <button
          type="button"
          aria-expanded={panel === "deliverables"}
          className={button}
          onClick={(event) => onPanel("deliverables", opener ?? event.currentTarget)}
        >
          {t("deliverablesButton")}
        </button>
        <button
          type="button"
          aria-expanded={panel === "records"}
          className={button}
          onClick={(event) => onPanel("records", opener ?? event.currentTarget)}
        >
          {t("records")}
        </button>
      </>
    );

  return (
    <header
      aria-label={t("topBar")}
      data-region="topbar"
      tabIndex={-1}
      className="relative z-40 flex h-14 shrink-0 items-center gap-3 border-b border-ink/[0.06] bg-paper px-5 text-slate"
    >
      <Mark />
      <button
        type="button"
        data-region-start
        aria-expanded={panel === "projects"}
        title={t("projects")}
        className={`${button} -ms-1 flex shrink-0 items-center gap-2 font-semibold text-ink`}
        onClick={(event) => onPanel("projects", event.currentTarget)}
      >
        {/* the project's name is never cut: the status folds before it does */}
        <span dir="auto">
          {project?.name ?? t("generalChat")}
        </span>
        <span aria-hidden="true" className="text-xs text-slate">▾</span>
      </button>
      {project?.archived_at && (
        <button
          type="button"
          aria-expanded={panel === "close"}
          className="shrink-0 whitespace-nowrap rounded-lg bg-stone px-3 py-1 text-ink hover:bg-ink/[0.08] focus-visible:outline-2 focus-visible:outline-ink"
          onClick={(event) => onPanel("close", event.currentTarget)}
        >
          {t("archivedReadOnly")}
        </button>
      )}

      {project && !narrow && <StatusStrip status={props.status} sources={props.sources} />}
      {project && narrow && Object.keys(props.status).length > 0 && (
        <Popover>
          <PopoverTrigger className={button}>{t("deliverableStatus")}</PopoverTrigger>
          <PopoverContent>
            <StatusStrip status={props.status} sources={props.sources} stacked />
          </PopoverContent>
        </Popover>
      )}
      {props.sample && (
        <span className="shrink-0 whitespace-nowrap rounded-lg border border-copper px-3 py-1 text-copper">{t("sampleData")}</span>
      )}

      <div className="ms-auto flex shrink-0 items-center gap-2">
        {project && <Following />}
        {project && !narrow && <TeamNow />}
        {project && props.waiting > 0 && (
          <button type="button" className={`${button} text-copper`} onClick={props.onWaiting}>
            {fill(t("waitingForYou"), { n: props.waiting })}
          </button>
        )}
        {!(narrow || compact) && (
          <>
            {searchField}
            {projectPanels()}
          </>
        )}
        {project && narrow && (
          <button type="button" aria-expanded={props.chatOpen} className={button} onClick={props.onChat}>
            {t("projectChat")}
          </button>
        )}
        <Popover>
          <PopoverTrigger ref={more} className={button}>
            {t("more")}
          </PopoverTrigger>
          <PopoverContent align="end" className="flex min-w-48 flex-col items-stretch gap-1 p-2 [&>button]:text-start">
            {(narrow || compact) && (
              <>
                {search}
                {projectPanels(more.current)}
              </>
            )}
            {project && (
              <>
                {!project.archived_at && (
                  <button type="button" className={button} onClick={() => onPanel("close", more.current!)}>
                    {t("closeProject")}
                  </button>
                )}
                <button type="button" className={button} onClick={() => onPanel("confidential", more.current!)}>
                  {t("confidential")}
                </button>
              </>
            )}
            <button type="button" className={button} onClick={() => onPanel("backup", more.current!)}>
              {t("backupTitle")}
            </button>
            <PopoverClose asChild>
              <button type="button" className={button} onClick={() => chooseFolder(false)}>
                {t("importMenu")}
              </button>
            </PopoverClose>
            <PopoverClose asChild>
              <button type="button" title={t("readyImportOldHelp")} className={button} onClick={() => chooseFolder(true)}>
                {t("readyImportOld")}
              </button>
            </PopoverClose>
            <hr className="mx-3 my-1 border-ink/[0.06]" />
            {ai(more.current)}
            <PopoverClose asChild>{otherLanguage}</PopoverClose>
            <PopoverClose asChild>
              <button type="button" title={t("setupAgainHelp")} className={button} onClick={() => openSetup()}>
                {t("setupAgain")}
              </button>
            </PopoverClose>
          </PopoverContent>
        </Popover>
      </div>
    </header>
  );
}
