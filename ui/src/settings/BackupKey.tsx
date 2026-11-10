// Backup, the Backup key: where it is kept (this computer, the QS Mind account, a saved recovery code), and, without
// an account, its recovery code: shown once with Copy, then its last group typed to confirm it was saved, checked as
// soon as the five characters are in (no Confirm button). The code lives only in this part while it shows; it is
// never logged or stored, and the core keeps only the last group, in memory, to check it.
import { useRef, useState } from "react";
import { type BackupState, confirmRecoveryCode, makeRecoveryCode } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { MetaLine } from "@/design/MetaLine";
import { Button } from "@/design/ui/button";
import { Input } from "@/design/ui/input";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

function Code({ code, onSaved }: { code: string; onSaved: () => void }) {
  const t = useText();
  const [copied, setCopied] = useState(false);
  const [typed, setTyped] = useState("");
  const [state, setState] = useState<"idle" | "checking" | TextPair>("idle");
  const sent = useRef("");

  async function type(value: string) {
    setTyped(value.toUpperCase());
    const group = value.trim().toUpperCase();
    if (group.replace(/[^A-Z0-9]/g, "").length !== 5 || group === sent.current) return;
    sent.current = group;
    setState("checking");
    const answer = await confirmRecoveryCode(group);
    if (sent.current !== group) return; // a later group was typed meanwhile
    if (answer.data) return onSaved();
    sent.current = ""; // refused: the next change is sent again
    setState(answer.error ?? texts.notSaved);
  }

  return (
    <section aria-labelledby="code" className="flex flex-col gap-3 rounded-xl bg-muted px-4 py-4">
      <h3 id="code" className="font-bold">
        {t(texts.codeTitle)}
      </h3>
      <p className="text-xs text-muted-foreground">{t(texts.codeOnce)}</p>
      {/* no break-all: a long line breaks after a dash, between groups, never inside one */}
      <output dir="ltr" aria-label={t(texts.codeTitle)} className="rounded-lg bg-card px-3 py-3 text-center font-mono select-all">
        {code}
      </output>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          onClick={() =>
            void navigator.clipboard
              ?.writeText(code)
              .then(() => setCopied(true))
              .catch(() => undefined)
          }
        >
          {t(texts.copy)}
        </Button>
        <p aria-live="polite" className="text-xs text-muted-foreground">
          {copied ? t(texts.copied) : null}
        </p>
      </div>
      <Field
        label={t(texts.codeLastGroup)}
        help={state === "checking" ? t(texts.checking) : undefined}
        error={typeof state === "object" ? t(state) : undefined}
      >
        <Input dir="ltr" autoComplete="off" spellCheck={false} maxLength={20} className="font-mono" value={typed} onChange={(event) => void type(event.target.value)} />
      </Field>
    </section>
  );
}

export function BackupKey({ state, onChanged }: { state: BackupState; onChanged: () => void }) {
  const t = useText();
  const [code, setCode] = useState<string>();
  const [problem, setProblem] = useState<TextPair>();
  const key = state.backup_key;

  async function make() {
    setProblem(undefined);
    const answer = await makeRecoveryCode();
    if (answer.data) setCode(answer.data.code);
    else setProblem(answer.error ?? texts.notSaved);
  }

  const where = (label: TextPair, yes: boolean) => `${t(label)}: ${t(yes ? texts.yes : texts.no)}`;
  return (
    <section aria-labelledby="backup-key" className="flex flex-col gap-3">
      <h2 id="backup-key" className="text-lg font-bold">
        {t(texts.backupKey)}
      </h2>
      <MetaLine items={[where(texts.keyLocal, key.local), where(texts.keyInAccount, key.in_account), where(texts.keyCodeSaved, key.code_saved)]} />
      {!key.in_account && !code ? (
        <>
          <p className="text-xs text-muted-foreground">{t(texts.keyNoAccount)}</p>
          <Button variant="outline" className="self-start" onClick={() => void make()}>
            {t(texts.makeCode)}
          </Button>
        </>
      ) : null}
      {code ? (
        <Code
          code={code}
          onSaved={() => {
            setCode(undefined); // dropped as soon as it is confirmed
            onChanged();
          }}
        />
      ) : null}
      {problem ? (
        <p role="alert" className="text-xs font-bold">
          {t(problem)}
        </p>
      ) : null}
    </section>
  );
}
