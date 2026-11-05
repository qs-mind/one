// The first launch: a full-window flow of six screens, language, QS Mind account, Connect AI, Introduction card,
// Usage Stats, then Ready. Each step has Back and Skip, and a row of step dots; a skipped step counts as passed and
// the app works with every step skipped. The core keeps where the engineer is (GET /setup, PUT /setup/{step}), so a
// first launch closed half-way opens at the next step. No screen mentions a plan or a price.
//
// The flow opens again from the top bar's More ("Setup"), over the app, and one step opens alone: the chat's
// "Connect AI", while the AI consent is missing.
import { type ReactNode, useEffect, useState } from "react";
import { api } from "../api";
import { send } from "../core";
import { dir, fill, language, setLanguage, t, useLanguage } from "../i18n";
import { useAiSettings } from "../settings/AiSettings";
import { Mark } from "../shell/TopBar";
import { Account } from "./Account";
import { ConnectAi } from "./ConnectAi";
import { IntroCard } from "./IntroCard";
import { Language } from "./Language";
import { Alert, closeSetup, type Nav, primary, type Setup, type Step, StepScreen, STEPS, useSetupRequest } from "./parts";
import { UsageStats } from "./UsageStats";

export { openSetup } from "./parts";

/** The system's language, the very first time: ar* is Arabic, anything else English. */
export function systemLanguage(): "ar" | "en" {
  return (navigator.languages?.[0] ?? navigator.language ?? "").toLowerCase().startsWith("ar") ? "ar" : "en";
}

const blank: Setup = { done: false, steps: { language: null, account: null, ai: null, card: null, usage: null } };

/** Shows the first launch until every step is passed, then the app; the app keeps a way back into the flow. When the
 * core cannot say (an older core, a failed read), the app shows: nothing in the flow is needed for it to work. */
export function SetupGate({
  children,
  onImport,
}: {
  children: ReactNode;
  /** The Ready screen's tender folder or old work (Task 11's importer). */
  onImport?: (from: DataTransfer | FileList, old: boolean) => void;
}) {
  const [state, setState] = useState<{ phase: "reading" | "flow" | "app"; setup: Setup }>({ phase: "reading", setup: blank });
  const asked = useSetupRequest();

  useEffect(() => {
    let live = true;
    void api("/setup")
      .then((r) => (r.ok ? (r.json() as Promise<Setup>) : undefined))
      .catch(() => undefined)
      .then((setup) => {
        if (!live) return;
        if (setup?.steps && !setup.done) setState({ phase: "flow", setup });
        else setState({ phase: "app", setup: setup?.steps ? setup : blank });
      });
    return () => {
      live = false;
    };
  }, []);

  if (state.phase === "reading") return null;
  if (state.phase === "flow")
    return <FirstLaunch initial={state.setup} onDone={(setup) => setState({ phase: "app", setup })} onImport={onImport} />;
  return (
    <>
      <div className="contents" inert={asked !== null}>
        {children}
      </div>
      {asked && (
        <div role="dialog" aria-modal="true" aria-label={t("setupTitle")} className="fixed inset-0 z-[60] overflow-y-auto">
          <FirstLaunch
            key={`${asked.from} ${asked.only}`}
            initial={state.setup}
            from={asked.from}
            only={asked.only}
            onImport={onImport}
            onDone={(setup) => {
              setState({ phase: "app", setup });
              closeSetup();
            }}
          />
        </div>
      )}
    </>
  );
}

type Screen = Step | "ready";
const SCREENS: readonly Screen[] = [...STEPS, "ready"];

export function FirstLaunch({
  initial,
  from,
  only = false,
  onDone,
  onImport,
}: {
  initial: Setup;
  /** Where to open; else at the first step not passed yet. */
  from?: Step;
  only?: boolean;
  onDone: (setup: Setup) => void;
  /** The Ready screen's tender folder (Task 11's import): without it, Ready offers only to start. */
  onImport?: (from: DataTransfer | FileList, old: boolean) => void;
}) {
  useLanguage();
  const [setup, setSetup] = useState(initial);
  const [at, setAt] = useState(() => {
    if (from) return SCREENS.indexOf(from);
    const next = STEPS.findIndex((step) => initial.steps[step] === null);
    return next === -1 ? SCREENS.length - 1 : next;
  });
  const [notSaved, setNotSaved] = useState(false);
  const [way, setWay] = useState<"forward" | "back">("forward"); // which side the next screen slides in from
  const screen = SCREENS[at]!;

  useEffect(() => {
    // the very first time, the page speaks the system's language until the engineer picks
    if (initial.steps.language === null && !from && language() !== systemLanguage()) setLanguage(systemLanguage());
  }, []);

  async function pass(step: Step, state: "done" | "skipped"): Promise<boolean> {
    setNotSaved(false);
    const body = step === "language" ? { state, lang: language() } : { state };
    const response = await send(`/setup/${step}`, "PUT", body);
    const answer = response?.ok ? ((await response.json().catch(() => undefined)) as Setup | undefined) : undefined;
    if (!answer?.steps) {
      setNotSaved(true);
      return false;
    }
    setSetup(answer);
    if (only) onDone(answer);
    else {
      setWay("forward");
      setAt((now) => now + 1);
    }
    return true;
  }

  const back = () => {
    setWay("back");
    setAt(at - 1);
  };
  const nav = (step: Step): Nav => ({
    back: at > 0 && !only ? back : undefined,
    pass: (state) => pass(step, state),
  });

  return (
    <div dir={dir()} data-firstlaunch="" className="flex min-h-dvh flex-col overflow-y-auto bg-paper text-ink">
      <header className="flex items-center gap-3 px-6 py-4 text-slate">
        <Mark />
        <span className="font-semibold text-ink">{t("appName")}</span>
        <span aria-hidden="true">·</span>
        <span>{t("setupTitle")}</span>
      </header>
      <main className="flex flex-1 justify-center px-4 pt-6 pb-12 sm:pt-16">
        <div className="flex w-full max-w-[36rem] flex-col gap-8">
          {!only && <Dots at={at} />}
          <div key={screen} data-way={way} className="fl-step">
            {screen === "language" && <Language nav={nav("language")} />}
            {screen === "account" && <Account nav={nav("account")} />}
            {screen === "ai" && <ConnectAi nav={nav("ai")} />}
            {screen === "card" && <IntroCard nav={nav("card")} />}
            {screen === "usage" && <UsageStats nav={nav("usage")} />}
            {screen === "ready" && (
              <Ready
                aiSkipped={setup.steps.ai === "skipped"}
                back={back}
                onStart={() => onDone(setup)}
                // the import goes on in the app: the folder is taken first, then the flow ends
                onImport={onImport && ((from, old) => (onImport(from, old), onDone(setup)))}
              />
            )}
          </div>
          {notSaved && <Alert>{t("setupNotSaved")}</Alert>}
        </div>
      </main>
    </div>
  );
}

/** One dot for each step: passed ones in Ink, the current one a longer Ink pill, those to come in a light Ink tint
 * (Stone is hardly seen on Paper). A dot grows
 * into the pill and takes its colour over 200 ms (a width on an 8 px dot: scaling it would squash its round ends). */
function Dots({ at }: { at: number }) {
  const n = Math.min(at + 1, STEPS.length);
  return (
    <div className="flex items-center gap-3">
      <ol aria-hidden="true" className="flex items-center gap-1.5">
        {STEPS.map((step, index) => (
          <li
            key={step}
            className={`h-2 rounded-full transition-[width,background-color] duration-200 ease-out ${index === at ? "w-6 bg-ink" : index < at ? "w-2 bg-ink" : "w-2 bg-ink/15"}`}
          />
        ))}
      </ol>
      {at < STEPS.length && <span className="text-xs text-slate">{fill(t("setupStepOf"), { n, total: STEPS.length })}</span>}
    </div>
  );
}

function Ready({
  aiSkipped,
  back,
  onStart,
  onImport,
}: {
  aiSkipped: boolean;
  back: () => void;
  onStart: () => void;
  onImport?: (from: DataTransfer | FileList, old: boolean) => void;
}) {
  const [over, setOver] = useState(false);
  const ai = useAiSettings(); // "no AI is connected" only when that is so: a link may be set up from AI settings
  const nav: Nav = { back, pass: async () => true };
  const start = (
    <button type="button" onClick={onStart} className={primary}>
      {onImport ? t("readyLater") : t("readyStart")}
    </button>
  );
  return (
    <StepScreen title={t("readyTitle")} help={aiSkipped && ai.connected !== true ? t("aiLinkLater") : undefined} nav={nav} skip={false} next={start}>
      {onImport && (
        <div className="flex flex-col gap-4">
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setOver(false);
              onImport(event.dataTransfer, false);
            }}
            className={`flex flex-col items-center gap-4 rounded-lg border-2 border-dashed px-6 py-12 text-center ${
              over ? "border-ink bg-stone" : "border-slate/30"
            }`}
          >
            <p className="text-lg font-semibold">{t("readyDrop")}</p>
            <FolderButton label={t("readyChooseFolder")} onFiles={(files) => onImport(files, false)} />
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <FolderButton label={t("readyImportOld")} quietLook onFiles={(files) => onImport(files, true)} />
            <span className="text-slate">{t("readyImportOldHelp")}</span>
          </div>
        </div>
      )}
    </StepScreen>
  );
}

/** "Choose folder": the browser's folder picker; the import reads each file's place in the folder. */
function FolderButton({ label, onFiles, quietLook = false }: { label: string; onFiles: (files: FileList) => void; quietLook?: boolean }) {
  return (
    <label className={`${quietLook ? "-ms-3 rounded-md px-3 py-2.5 text-ink underline decoration-slate/40 underline-offset-4 hover:bg-stone" : "rounded-md bg-stone px-5 py-2.5 hover:bg-ink/[0.08]"} cursor-pointer focus-within:outline-2 focus-within:outline-ink`}>
      {label}
      <input
        type="file"
        className="sr-only"
        // folder picking: not in React's input types
        {...{ webkitdirectory: "", directory: "" }}
        multiple
        onChange={(event) => event.target.files?.length && onFiles(event.target.files)}
      />
    </label>
  );
}
