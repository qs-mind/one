// First launch: three steps (the language, who you are, connect AI) over the setup strip, which shows ONE getting
// itself ready meanwhile. The step to open on comes from the core (contract S3, S184): GET /setup says whether the
// language was chosen, the profile whether it is complete. Someone upgrading has both and lands on step 3 only when
// the profile is complete too. Each step saves as the engineer goes; `onDone` runs once step 3 is passed.
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

/** The first step the engineer has not passed. */
export async function firstStep(): Promise<Step> {
  const [setup, profile] = await Promise.all([getSetupSteps(), client.GET("/engineer/profile").catch(() => undefined)]);
  if (!setup.data?.steps.language) return 1;
  return profile?.data?.complete ? 3 : 2;
}

export function Welcome({ onDone }: { onDone: () => void }) {
  const t = useText();
  const [step, setStep] = useState<Step>();

  useEffect(() => {
    let live = true;
    void firstStep().then((first) => live && setStep(first));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center gap-5 px-6 py-7 sm:px-14">
        <Wordmark />
        {step ? <span className="ms-auto text-xs text-muted-foreground">{t(common.stepOf, { step, total: 3 })}</span> : null}
      </header>
      <main className="mx-auto flex w-full max-w-160 flex-1 flex-col gap-10 px-6 py-10">
        {step === 1 ? <Language onNext={() => setStep(2)} /> : null}
        {step === 2 ? <WhoYouAre onBack={() => setStep(1)} onNext={() => setStep(3)} /> : null}
        {step === 3 ? <ConnectAi onBack={() => setStep(2)} onDone={onDone} /> : null}
      </main>
      <footer className="mx-auto w-full max-w-160 px-6 pt-5 pb-7">
        <SetupStrip />
      </footer>
    </div>
  );
}
