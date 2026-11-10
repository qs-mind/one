// Settings, AI: the one key box (U7's KeyBox), the providers connected now, the core's AI settings (the recommended
// models or a model per role, and Confidential Projects on this computer only), the prices ONE does not know, and the
// web search key.
import { useCallback, useEffect, useState } from "react";
import { getConsent } from "@/api/existing";
import { type AiSettings, getAiSettings } from "@/api/settingsKept";
import { KeyBox } from "@/firstlaunch/KeyBox";
import { settings as texts } from "@/texts/settings";
import { useText } from "@/texts/useText";
import type { Change } from "./Field";
import { Prices } from "./Prices";
import { Providers } from "./Providers";
import { RolePicker } from "./RolePicker";
import { SearchKey } from "./SearchKey";
import { SettingsSection } from "./Section";
import type { Setting } from "./useSettings";

export function AiSection({ settings, change }: { settings: Setting[]; change: Change }) {
  const t = useText();
  const [agreed, setAgreed] = useState(false);
  const [ai, setAi] = useState<AiSettings>();

  const load = useCallback(async () => {
    const answer = await getAiSettings();
    if (answer.data) setAi(answer.data);
  }, []);

  useEffect(() => {
    let live = true;
    void getConsent().then(({ data }) => live && setAgreed(data?.at != null));
    void load();
    return () => {
      live = false;
    };
  }, [load]);

  return (
    <>
      <section aria-labelledby="connect" className="flex flex-col gap-3">
        <h2 id="connect" className="text-lg font-bold">
          {t(texts.connect)}
        </h2>
        <KeyBox agreed={agreed} lockedHelp={t(texts.keyLocked)} onConnected={(connected) => connected && void load()} />
      </section>
      {ai ? <Providers connectors={ai.connectors} onChanged={() => void load()} /> : null}
      <SettingsSection
        section="ai"
        settings={settings}
        change={change}
        after={(setting) => (setting.key === "ai.models" && setting.value === "own" && ai ? <RolePicker ai={ai} /> : null)}
      />
      {ai ? <Prices sheet={ai.sheet} onSaved={() => void load()} /> : null}
      <SearchKey />
    </>
  );
}
