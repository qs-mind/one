// The one key box, in first launch (step 3) and in Settings, AI. A pasted key is checked at once
// (POST /settings/ai/connect reads the provider from the key's own form) and shows the provider it reached or the
// core's plain words; there is no Check or Save button. A key ONE does not recognise opens the provider's address
// under it (ProviderAddress). The key is never shown back.
import { useEffect, useRef, useState } from "react";
import { client, type Schemas } from "@/api/client";
import { Field } from "@/design/Field";
import { Input } from "@/design/ui/input";
import { firstlaunch } from "@/texts/firstlaunch";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { ProviderAddress } from "./ProviderAddress";

/** How long after the last change a typed key is checked (a paste is one change). */
export const CHECK_MS = 300;

type KeyCheck =
  | { state: "idle" }
  | { state: "checking" }
  | { state: "works"; link: Schemas["AiLink"] }
  | { state: "refused"; words: TextPair; unknown?: boolean }; // unknown: a key ONE does not recognise (422)

type KeyBoxProps = {
  /** The AI consent is given: until then the box is off and `lockedHelp` says why. */
  agreed: boolean;
  lockedHelp: string;
  /** Called with true when the key works or was linked by its provider's address, false when that is undone. */
  onConnected?: (connected: boolean) => void;
};

export function KeyBox({ agreed, lockedHelp, onConnected }: KeyBoxProps) {
  const t = useText();
  const [key, setKey] = useState("");
  const [keyCheck, setKeyCheck] = useState<KeyCheck>({ state: "idle" });
  const runs = useRef(0); // only the latest key's answer shows
  const told = useRef(onConnected);
  told.current = onConnected;

  useEffect(() => {
    const pasted = key.trim();
    const mine = ++runs.current;
    told.current?.(false);
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
      if (mine !== runs.current) return;
      setKeyCheck(next);
      if (next.state === "works") told.current?.(true);
    }, CHECK_MS);
    return () => clearTimeout(timer);
  }, [key, agreed]);

  const help =
    keyCheck.state === "checking"
      ? t(firstlaunch.keyChecking)
      : keyCheck.state === "works"
        ? t(firstlaunch.keyWorks, { provider: keyCheck.link.provider })
        : agreed
          ? undefined
          : lockedHelp;
  return (
    <>
      <Field label={t(firstlaunch.keyLabel)} help={help} error={keyCheck.state === "refused" ? t(keyCheck.words) : undefined}>
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
      {keyCheck.state === "refused" && keyCheck.unknown ? (
        <ProviderAddress key={key.trim()} apiKey={key.trim()} onLinked={(linked) => told.current?.(linked)} />
      ) : null}
    </>
  );
}
