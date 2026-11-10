// Step 1: the language. It starts on the system's language; choosing the other turns the page at once. Next tells the
// core the choice (PUT /setup/language {state: "done", lang}), which also keeps it.
import { useState } from "react";
import { passStep } from "@/api/existing";
import { ListRow } from "@/design/ListRow";
import { Button } from "@/design/ui/button";
import { RadioGroup, RadioGroupItem } from "@/design/ui/radio-group";
import { firstlaunch } from "@/texts/firstlaunch";
import { useLang } from "@/texts/language";
import type { Lang } from "@/texts/types";
import { text, useText } from "@/texts/useText";
import { StepActions, StepHead } from "./parts";

// Each language is named in itself, whatever the page's language is.
const CHOICES: { lang: Lang; name: string }[] = [
  { lang: "ar", name: text(firstlaunch.arabic, "ar") },
  { lang: "en", name: text(firstlaunch.english, "en") },
];

export function Language({ onNext }: { onNext: () => void }) {
  const t = useText();
  const { lang, setLang } = useLang();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function next() {
    setBusy(true);
    setFailed(false);
    const saved = await passStep("language", "done", lang);
    setBusy(false);
    if (saved.data) onNext();
    else setFailed(true);
  }

  return (
    <>
      <StepHead title={t(firstlaunch.languageTitle)} lead={t(firstlaunch.languageLead)} />
      <RadioGroup className="gap-3" value={lang} onValueChange={(value) => setLang(value as Lang)} aria-label={t(firstlaunch.languageTitle)}>
        {CHOICES.map((choice) => (
          <ListRow
            key={choice.lang}
            frame="boxed"
            render={<label lang={choice.lang} />}
            current={choice.lang === lang}
            leading={<RadioGroupItem value={choice.lang} />}
            title={choice.name}
          />
        ))}
      </RadioGroup>
      <StepActions note={failed ? t(firstlaunch.stepNotSaved) : null} strong={failed}>
        <Button size="lg" loading={busy} onClick={() => void next()}>
          {t(firstlaunch.next)}
        </Button>
      </StepActions>
    </>
  );
}
