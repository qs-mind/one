// First launch: three steps (the language, who you are, connect AI) over the setup strip, which shows ONE getting
// itself ready meanwhile. The step to open on comes from the core (contract S3, S184): GET /setup says whether the
// language was chosen and whether the AI step was passed, the profile whether it is complete. Someone upgrading has
// both steps and lands on step 2 only: its Next ends first launch, with no way back to step 1 or on to step 3 (which
// could turn their AI step to "skipped"). Each step saves as the engineer goes; `onDone` runs once the last is passed.
import { useEffect, useState } from "react";
import { client } from "@/api/client";
import { getSetupSteps } from "@/api/existing";
import { Wordmark } from "@/design/Wordmark";
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";
import { ConnectAi } from "./ConnectAi";
import { Language } from "./Language";
import { SetupStrip } from "./SetupStrip";
import { WhoYouAre } from "./WhoYouAre";

export type Step = 1 | 2 | 3;

/** The first step the engineer has not passed, and whether the AI step is passed already (an upgrade). */
export async function firstStep(): Promise<{ step: Step; upgrading: boolean }> {
  const [setup, profile] = await Promise.all([getSetupSteps(), client.GET("/engineer/profile").catch(() => undefined)]);
  const steps = setup.data?.steps;
  if (steps?.language && steps.ai) return { step: 2, upgrading: true };
  if (!steps?.language) return { step: 1, upgrading: false };
  return { step: profile?.data?.complete ? 3 : 2, upgrading: false };
}

export function Welcome({ onDone }: { onDone: () => void }) {
  const t = useText();
  const [step, setStep] = useState<Step>();
  const [upgrading, setUpgrading] = useState(false);

  useEffect(() => {
    let live = true;
    void firstStep().then((first) => {
      if (!live) return;
      setUpgrading(first.upgrading);
      setStep(first.step);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center gap-5 px-6 py-7 sm:px-14">
        <Wordmark />
        {step && !upgrading ? <span className="ms-auto text-xs text-muted-foreground">{t(common.stepOf, { step, total: 3 })}</span> : null}
      </header>
      <main className="mx-auto flex w-full max-w-160 flex-1 flex-col gap-10 px-6 py-10">
        {step === 1 ? <Language onNext={() => setStep(2)} /> : null}
        {step === 2 ? (
          <WhoYouAre onBack={upgrading ? undefined : () => setStep(1)} onNext={upgrading ? onDone : () => setStep(3)} />
        ) : null}
        {step === 3 ? <ConnectAi onBack={() => setStep(2)} onDone={onDone} /> : null}
      </main>
      <footer className="mx-auto w-full max-w-160 px-6 pt-5 pb-7">
        <SetupStrip />
      </footer>
    </div>
  );
}
