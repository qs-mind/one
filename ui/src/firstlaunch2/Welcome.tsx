// Placeholder: U7 replaces it with first launch, one step at a time (/welcome/:step). Leaving /welcome makes the
// gate ask the core again (app/gates.tsx), so the last step only has to go to Home.
import { useParams } from "react-router";
import { app } from "@/texts/app";
import { useText } from "@/texts/useText";

export function Welcome() {
  const t = useText();
  const { step } = useParams();
  return (
    <main data-place="welcome" data-step={step} className="min-h-dvh bg-background p-12 text-foreground">
      <h1 className="text-3xl font-bold">{t(app.welcome)}</h1>
    </main>
  );
}
