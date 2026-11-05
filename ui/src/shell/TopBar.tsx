// The top bar, 48 px: the mark, the project (or the General chat) with its switcher, the project's status, the agent
// the view follows, who is working now, "Waiting for you", search, then AI settings, the other language, the Deliverables and Project Records. Below 900 px the
// status folds into one Status button and the rest into More; below 1280 px search, the panels, AI settings and the
// other language fold into More, and the status folds what does not fit into More status: the project's name is
// never cut. The chrome mirrors in Arabic.
import { useRef } from "react";
import type { ProjectSources, ProjectStatus } from "../canvas/types";
import { isMac } from "../canvas/keys";
import { Following, TeamNow } from "../canvas/live/TeamNow";
import { fill, language, setLanguage, t, useLanguage } from "../i18n";
import type { Project } from "../records/project";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { useCompact } from "./regions";
import { StatusStrip } from "./StatusStrip";

export type PanelKind = "ai" | "projects" | "records" | "deliverables";

const MARK = 
  "M18 109.32L31.22 171.34M18 109.32L31.63 138.83M18 109.32L41.86 84.2M18 109.32L43.74 51.39M31.22 171.34L31.63 138.83M31.22 171.34L63.25 184.55M31.22 171.34L78.35 213.75M31.63 138.83L41.86 84.2M31.63 138.83L63.25 184.55M31.63 138.83L69.83 130.69M41.86 84.2L43.74 51.39M41.86 84.2L69.83 130.69M41.86 84.2L75.43 40.26M41.86 84.2L95.57 72.76M43.74 51.39L75.43 40.26M43.74 51.39L98.61 19.66M63.25 184.55L69.83 130.69M63.25 184.55L78.35 213.75M63.25 184.55L111.82 210.98M63.25 184.55L116.96 173.1M69.83 130.69L95.57 72.76M69.83 130.69L116.96 173.1M69.83 130.69L123.01 119.36M75.43 40.26L95.57 72.76M75.43 40.26L98.61 19.66M75.43 40.26L130.64 32.86M78.35 213.75L111.82 210.98M78.35 213.75L141.39 220.34M95.57 72.76L123.01 119.36M95.57 72.76L130.64 32.86M95.57 72.76L158.61 79.35M98.61 19.66L130.64 32.86M98.61 19.66L161.65 26.25M111.82 210.98L116.96 173.1M111.82 210.98L141.39 220.34M111.82 210.98L165.25 195.22M116.96 173.1L123.01 119.36M116.96 173.1L165.25 195.22M116.96 173.1L171.83 141.37M123.01 119.36L158.61 79.35M123.01 119.36L171.83 141.37M130.64 32.86L158.61 79.35M130.64 32.86L161.65 26.25M130.64 32.86L182.68 51.49M141.39 220.34L165.25 195.22M141.39 220.34L196.26 188.61M158.61 79.35L171.83 141.37M158.61 79.35L182.68 51.49M158.61 79.35L206.9 101.48M161.65 26.25L182.68 51.49M161.65 26.25L208.78 68.66M165.25 195.22L171.83 141.37M165.25 195.22L196.26 188.61M165.25 195.22L205.17 157M171.83 141.37L205.17 157M171.83 141.37L206.9 101.48M182.68 51.49L206.9 101.48M182.68 51.49L208.78 68.66M196.26 188.61L205.17 157M196.26 188.61L222 130.68M205.17 157L206.9 101.48M205.17 157L222 130.68M206.9 101.48L208.78 68.66M206.9 101.48L222 130.68M208.78 68.66L222 130.68";

/** The QS Mind mark, static: it never rotates, glows or sits on a tile. */
function Mark() {
  return (
    <svg viewBox="0 0 240 240" width="24" height="24" aria-hidden="true" className="shrink-0">
      <defs>
        <linearGradient id="qs-mind-face" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F0A35A" />
          <stop offset="1" stopColor="#C0582A" />
        </linearGradient>
      </defs>
      <polygon points="182.68,51.49 206.9,101.48 158.61,79.35" fill="url(#qs-mind-face)" />
      <path d={MARK} fill="none" stroke="#0E0F12" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const button = "whitespace-nowrap rounded-md px-2 py-1 hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink";

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
  onPalette(): void;
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
    <button type="button" className={button} onClick={props.onPalette}>
      {fill(t("searchKeys"), { keys })}
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
      onClick={() => setLanguage(language() === "ar" ? "en" : "ar")}
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
      className="relative z-40 flex h-12 shrink-0 items-center gap-2 border-b border-ink/10 bg-paper px-3 text-slate"
    >
      <Mark />
      <button
        type="button"
        data-region-start
        aria-expanded={panel === "projects"}
        title={t("projects")}
        className={`${button} flex shrink-0 items-center gap-1 font-semibold text-ink`}
        onClick={(event) => onPanel("projects", event.currentTarget)}
      >
        {/* the project's name is never cut: the status folds before it does */}
        <span dir="auto">
          {project?.name ?? t("generalChat")}
        </span>
        <span aria-hidden="true">▾</span>
      </button>

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
        <span className="shrink-0 whitespace-nowrap rounded-md border border-copper px-2 py-0.5 text-copper">{t("sampleData")}</span>
      )}

      <div className="ms-auto flex shrink-0 items-center gap-1">
        {project && <Following />}
        {project && !narrow && <TeamNow />}
        {project && props.waiting > 0 && (
          <button type="button" className={`${button} text-copper`} onClick={props.onWaiting}>
            {fill(t("waitingForYou"), { n: props.waiting })}
          </button>
        )}
        {narrow || compact ? (
          <>
            {project && narrow && (
              <button type="button" aria-expanded={props.chatOpen} className={button} onClick={props.onChat}>
                {t("projectChat")}
              </button>
            )}
            <Popover>
              <PopoverTrigger ref={more} className={button}>
                {t("more")}
              </PopoverTrigger>
              <PopoverContent align="end" className="flex flex-col items-start gap-1">
                {search}
                {projectPanels(more.current)}
                {ai(more.current)}
                {otherLanguage}
              </PopoverContent>
            </Popover>
          </>
        ) : (
          <>
            {search}
            {projectPanels()}
            {ai()}
            {otherLanguage}
          </>
        )}
      </div>
    </header>
  );
}
