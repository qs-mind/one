// First launch: three steps (the language, who you are, connect AI) over the setup strip, which shows ONE getting
// itself ready meanwhile. The step comes from the address (/welcome/<step>): the first-launch gate (app/gates.tsx)
// works out which step to open on, from the core (contract S3, S184), and the steps move the address on. Someone
// upgrading has the language and AI steps passed and lands on step 2 only: its Next ends first launch, with no way
// back to step 1 or on to step 3 (which could turn their AI step to "skipped"). Each step saves as the engineer goes;
// `onDone` runs once the last is passed.
import type { WelcomeStep } from "@/app/paths";
import { Wordmark } from "@/design/Wordmark";
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";
import { ConnectAi } from "./ConnectAi";
import { Language } from "./Language";
import { SetupStrip } from "./SetupStrip";
import { WhoYouAre } from "./WhoYouAre";

const NUMBER: Record<WelcomeStep, number> = { language: 1, profile: 2, ai: 3 };

export function Welcome({
  step,
  upgrading,
  onStep,
  onDone,
}: {
  step: WelcomeStep;
  upgrading: boolean;
  onStep: (step: WelcomeStep) => void;
  onDone: () => void;
}) {
  const t = useText();

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center gap-5 px-6 py-7 sm:px-14">
        <Wordmark />
        {upgrading ? null : <span className="ms-auto text-xs text-muted-foreground">{t(common.stepOf, { step: NUMBER[step], total: 3 })}</span>}
      </header>
      <main className="mx-auto flex w-full max-w-160 flex-1 flex-col gap-10 px-6 py-10">
        {step === "language" ? <Language onNext={() => onStep("profile")} /> : null}
        {step === "profile" ? (
          <WhoYouAre onBack={upgrading ? undefined : () => onStep("language")} onNext={upgrading ? onDone : () => onStep("ai")} />
        ) : null}
        {step === "ai" ? <ConnectAi onBack={() => onStep("profile")} onDone={onDone} /> : null}
      </main>
      <footer className="mx-auto w-full max-w-160 px-6 pt-5 pb-7">
        <SetupStrip />
      </footer>
    </div>
  );
}
