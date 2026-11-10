// First launch in the router, with one source for its step. The gate stands before every place: it reads today's
// GET /setup (steps `language` and `ai`) and Profile.complete (contract, section 0), and until the three steps are
// passed every address leads to the step still to do. In first launch the screen follows the step in the address and
// moves it on. Someone upgrading has both steps already: the gate pins them to step 2, and tells the screen, which then
// has no way back or on. Leaving first launch makes the gate ask again before any place shows.
import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router";
import { api } from "@/api";
import { client, type Schemas } from "@/api/client";
import { Welcome } from "@/firstlaunch/Welcome";
import { paths, WELCOME_STEPS, type WelcomeStep } from "./paths";

/** The step to do first; null when none is left. What the core could not answer does not hold the engineer. */
export function stepToDo(setup: Schemas["SetupSteps"] | null, profile: Schemas["Profile"] | null): WelcomeStep | null {
  if (setup && setup.steps.language === null) return "language";
  if (profile && !profile.complete) return "profile";
  if (setup && setup.steps.ai === null) return "ai";
  return null;
}

async function readSetup(): Promise<Schemas["SetupSteps"] | null> {
  const answer = await api("/setup");
  return answer.ok ? ((await answer.json()) as Schemas["SetupSteps"]) : null;
}

async function readProfile(): Promise<Schemas["Profile"] | null> {
  const { data } = await client.GET("/engineer/profile");
  return data ?? null;
}

const orNull = <T,>(read: () => Promise<T | null>) => read().catch(() => null);

/** What the gate tells first launch: whether this is someone upgrading, who has step 2 only. */
export type WelcomeContext = { upgrading: boolean };

type Known = { step: WelcomeStep | null; upgrading: boolean };

export function FirstLaunchGate() {
  const { pathname } = useLocation();
  const onWelcome = pathname.startsWith("/welcome");
  const [known, setKnown] = useState<Known>(); // undefined while it asks
  const [wasOnWelcome, setWasOnWelcome] = useState(onWelcome);
  if (wasOnWelcome !== onWelcome) {
    setWasOnWelcome(onWelcome);
    if (!onWelcome) setKnown(undefined); // first launch was left: ask again before any place shows
  }

  useEffect(() => {
    if (known) return;
    let live = true;
    void Promise.all([orNull(readSetup), orNull(readProfile)]).then(([setup, profile]) => {
      const step = stepToDo(setup, profile);
      const passed = setup !== null && setup.steps.language !== null && setup.steps.ai !== null;
      if (live) setKnown({ step, upgrading: step === "profile" && passed });
    });
    return () => {
      live = false;
    };
  }, [known]);

  if (!known) return <div aria-busy="true" className="h-dvh bg-background" />;
  if (onWelcome) {
    if (known.upgrading && pathname !== paths.welcome("profile")) return <Navigate to={paths.welcome("profile")} replace />;
    return <Outlet context={{ upgrading: known.upgrading } satisfies WelcomeContext} />;
  }
  if (known.step) return <Navigate to={paths.welcome(known.step)} replace />;
  return <Outlet />;
}

const isStep = (value: string | undefined): value is WelcomeStep => (WELCOME_STEPS as readonly (string | undefined)[]).includes(value);

/** /welcome/<step>: first launch at the address's step. When it ends, Home. */
export function WelcomePlace() {
  const { step } = useParams();
  const { upgrading } = useOutletContext<WelcomeContext>();
  const navigate = useNavigate();
  if (!isStep(step)) return <Navigate to={paths.welcome(WELCOME_STEPS[0])} replace />;
  return (
    <div data-place="welcome" data-step={step}>
      <Welcome
        step={step}
        upgrading={upgrading}
        onStep={(next) => navigate(paths.welcome(next))}
        onDone={() => navigate(paths.home, { replace: true })}
      />
    </div>
  );
}
