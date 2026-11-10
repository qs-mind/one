// The first-launch gate: until the three steps are passed, every address leads to the step still to do. It reads
// today's GET /setup (steps `language` and `ai`) and Profile.complete (contract, section 0). Someone upgrading has
// both steps already and lands on step 2 only. It asks again each time first launch is left.
import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { api } from "@/api";
import { client, type Schemas } from "@/api/client";
import { paths, type WelcomeStep } from "./paths";

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

type Known = { step: WelcomeStep | null };

export function FirstLaunchGate() {
  const onWelcome = useLocation().pathname.startsWith("/welcome");
  const [known, setKnown] = useState<Known>(); // undefined while it asks

  useEffect(() => {
    // In first launch, forget a step still to do, so leaving it asks again before any place shows.
    if (onWelcome) return setKnown((was) => (was?.step === null ? was : undefined));
    if (known) return;
    let live = true;
    void Promise.all([orNull(readSetup), orNull(readProfile)]).then(([setup, profile]) => {
      if (live) setKnown({ step: stepToDo(setup, profile) });
    });
    return () => {
      live = false;
    };
  }, [onWelcome, known]);

  if (onWelcome) return <Outlet />;
  if (!known) return <div aria-busy="true" className="h-dvh bg-background" />;
  if (known.step) return <Navigate to={paths.welcome(known.step)} replace />;
  return <Outlet />;
}
