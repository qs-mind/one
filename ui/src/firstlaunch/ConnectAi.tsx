// Step 3: connect AI. First the AI consent (contract Q3: inside this step, before any key is checked), then the one
// key box (KeyBox, shared with Settings). The other way is the engineer's own Claude Code. The step ends "done" with
// either, or "skipped" with neither (Q2); there is no Check or Save button. A link the core holds already (the step
// seen before, then Back and Next) counts as connected.
import { useEffect, useState } from "react";
import { type AiConnector, getAiSettings } from "@/api/settingsKept";
import { checkClaudeCode, type Consent, findClaudeCode, getConsent, giveConsent, openPage, passStep } from "@/api/existing";
import { Button } from "@/design/ui/button";
import { Separator } from "@/design/ui/separator";
import { firstlaunch } from "@/texts/firstlaunch";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { KeyBox } from "./KeyBox";
import { StepActions, StepHead } from "./parts";

/** A link the engineer made (as Settings, Providers.tsx, counts them), or Claude Code switched on. */
const isLink = (it: AiConnector) => it.id === "claude-code" || (it.kind === "model" && (it.key_set || it.id.startsWith("standard:")));

type ClaudeCheck = { state: "idle" } | { state: "checking" } | { state: "works" } | { state: "refused"; words: TextPair };

export function ConnectAi({ onBack, onDone }: { onBack: () => void; onDone: () => void }) {
  const t = useText();
  const [consent, setConsent] = useState<Consent>();
  const [consentFailed, setConsentFailed] = useState(false);
  const [keyWorks, setKeyWorks] = useState(false); // the key works, or was linked by its provider's address
  const [linked, setLinked] = useState(false); // the core held a link when the step opened
  const [claude, setClaude] = useState<ClaudeCheck>({ state: "idle" });
  const [ending, setEnding] = useState<"done" | "skipped">();
  const [stepFailed, setStepFailed] = useState(false);
  const agreed = consent?.at != null;

  useEffect(() => {
    let live = true;
    void getConsent().then(({ data }) => live && data && setConsent(data));
    void getAiSettings().then(({ data }) => live && data && setLinked(data.connectors.some(isLink)));
    return () => {
      live = false;
    };
  }, []);

  async function agree() {
    setConsentFailed(false);
    const version = consent?.text_version ?? 1;
    const given = await giveConsent(version);
    if (given.data) setConsent({ at: given.data.at, text_version: version });
    else setConsentFailed(true);
  }

  async function tryClaudeCode() {
    setClaude({ state: "checking" });
    const found = await findClaudeCode();
    if (!found.data?.found) return setClaude({ state: "refused", words: firstlaunch.claudeMissing });
    const checked = await checkClaudeCode();
    setClaude(checked.data ? { state: "works" } : { state: "refused", words: checked.error ?? firstlaunch.claudeFailed });
  }

  async function end(state: "done" | "skipped") {
    setEnding(state);
    setStepFailed(false);
    const passed = await passStep("ai", state);
    setEnding(undefined);
    if (passed.data) onDone();
    else setStepFailed(true);
  }

  const connected = keyWorks || linked || claude.state === "works";
  const note = stepFailed ? t(firstlaunch.stepNotSaved) : connected ? null : t(firstlaunch.laterNote);

  return (
    <>
      <StepHead title={t(firstlaunch.aiTitle)} lead={t(firstlaunch.aiLead)} />
      <section aria-labelledby="ai-consent" className="flex flex-col gap-3 rounded-2xl bg-muted px-6 py-5">
        <h2 id="ai-consent" className="text-lg font-bold">
          {t(firstlaunch.consentTitle)}
        </h2>
        <p>{t(firstlaunch.consentBody)}</p>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <Button variant="link" onClick={() => openPage("terms", t.lang)}>
            {t(firstlaunch.terms)}
          </Button>
          <Button variant="link" onClick={() => openPage("privacy", t.lang)}>
            {t(firstlaunch.privacy)}
          </Button>
          {consent && !agreed ? (
            <Button className="ms-auto" onClick={() => void agree()}>
              {t(firstlaunch.agree)}
            </Button>
          ) : null}
        </div>
        <p aria-live="polite" className="text-xs empty:hidden">
          {agreed ? t(firstlaunch.agreed) : consentFailed ? <span className="font-bold">{t(firstlaunch.consentNotSaved)}</span> : null}
        </p>
      </section>

      <div className="flex flex-col gap-5">
        <KeyBox agreed={agreed} lockedHelp={t(firstlaunch.keyAfterConsent)} onConnected={setKeyWorks} />
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <Separator className="flex-1" />
          <span>{t(firstlaunch.or)}</span>
          <Separator className="flex-1" />
        </div>
        <div className="flex flex-col gap-2">
          <Button variant="outline" size="lg" disabled={!agreed} loading={claude.state === "checking"} onClick={() => void tryClaudeCode()}>
            {claude.state === "refused" ? t(firstlaunch.tryAgain) : t(firstlaunch.useClaudeCode)}
          </Button>
          <p aria-live="polite" className="text-xs empty:hidden">
            {claude.state === "checking" ? <span className="text-muted-foreground">{t(firstlaunch.claudeChecking)}</span> : null}
            {claude.state === "works" ? t(firstlaunch.claudeWorks) : null}
            {claude.state === "refused" ? <span className="font-bold">{t(claude.words)}</span> : null}
          </p>
        </div>
      </div>

      <StepActions note={note} strong={stepFailed}>
        <Button variant="ghost" size="lg" onClick={onBack}>
          {t(firstlaunch.back)}
        </Button>
        {connected ? (
          <Button size="lg" loading={ending === "done"} onClick={() => void end("done")}>
            {t(firstlaunch.start)}
          </Button>
        ) : (
          <Button variant="outline" size="lg" loading={ending === "skipped"} onClick={() => void end("skipped")}>
            {t(firstlaunch.later)}
          </Button>
        )}
      </StepActions>
    </>
  );
}
