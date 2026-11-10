// Step 3: connect AI. First the AI consent (contract Q3: inside this step, before any key is checked), then one box:
// a pasted key is checked at once (POST /settings/ai/connect reads the provider from the key's own form) and shows
// the provider it reached or the core's plain words. The other way is the engineer's own Claude Code. The step ends
// "done" with either, or "skipped" with neither (Q2); there is no Check or Save button. A key ONE does not recognise
// opens the provider's address under it (ProviderAddress).
import { useEffect, useRef, useState } from "react";
import { client, type Schemas } from "@/api/client";
import { checkClaudeCode, type Consent, findClaudeCode, getConsent, giveConsent, openPage, passStep } from "@/api/existing";
import { Field } from "@/design/Field";
import { Button } from "@/design/ui/button";
import { Input } from "@/design/ui/input";
import { Separator } from "@/design/ui/separator";
import { firstlaunch } from "@/texts/firstlaunch";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { StepActions, StepHead } from "./parts";
import { ProviderAddress } from "./ProviderAddress";

/** How long after the last change a typed key is checked (a paste is one change). */
export const CHECK_MS = 300;

type KeyCheck =
  | { state: "idle" }
  | { state: "checking" }
  | { state: "works"; link: Schemas["AiLink"] }
  | { state: "refused"; words: TextPair; unknown?: boolean }; // unknown: a key ONE does not recognise (422)
type ClaudeCheck = { state: "idle" } | { state: "checking" } | { state: "works" } | { state: "refused"; words: TextPair };

export function ConnectAi({ onBack, onDone }: { onBack: () => void; onDone: () => void }) {
  const t = useText();
  const [consent, setConsent] = useState<Consent>();
  const [consentFailed, setConsentFailed] = useState(false);
  const [key, setKey] = useState("");
  const [keyCheck, setKeyCheck] = useState<KeyCheck>({ state: "idle" });
  const [byAddress, setByAddress] = useState(false); // the unknown key was linked by its provider's address
  const [claude, setClaude] = useState<ClaudeCheck>({ state: "idle" });
  const [ending, setEnding] = useState<"done" | "skipped">();
  const [stepFailed, setStepFailed] = useState(false);
  const runs = useRef(0); // only the latest key's answer shows
  const agreed = consent?.at != null;

  useEffect(() => {
    let live = true;
    void getConsent().then(({ data }) => live && data && setConsent(data));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const pasted = key.trim();
    const mine = ++runs.current;
    setByAddress(false);
    if (pasted === "" || !agreed) return setKeyCheck({ state: "idle" });
    setKeyCheck({ state: "checking" });
    const timer = setTimeout(async () => {
      let next: KeyCheck = { state: "refused", words: firstlaunch.keyNotChecked };
      try {
        const { data, error, response } = await client.POST("/settings/ai/connect", { body: { key: pasted } });
        if (data) next = { state: "works", link: data };
        else if (error && "error" in error) next = { state: "refused", words: error.error, unknown: response.status === 422 };
      } catch {
        // the core could not be reached: keyNotChecked
      }
      if (mine === runs.current) setKeyCheck(next);
    }, CHECK_MS);
    return () => clearTimeout(timer);
  }, [key, agreed]);

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

  const connected = keyCheck.state === "works" || byAddress || claude.state === "works";
  const keyHelp =
    keyCheck.state === "checking"
      ? t(firstlaunch.keyChecking)
      : keyCheck.state === "works"
        ? t(firstlaunch.keyWorks, { provider: keyCheck.link.provider })
        : agreed
          ? undefined
          : t(firstlaunch.keyAfterConsent);
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
        <Field label={t(firstlaunch.keyLabel)} help={keyHelp} error={keyCheck.state === "refused" ? t(keyCheck.words) : undefined}>
          <Input
            type="password"
            dir="ltr"
            autoComplete="off"
            spellCheck={false}
            disabled={!agreed}
            value={key}
            onChange={(event) => setKey(event.target.value)}
          />
        </Field>
        {keyCheck.state === "refused" && keyCheck.unknown ? <ProviderAddress key={key.trim()} apiKey={key.trim()} onLinked={setByAddress} /> : null}
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
