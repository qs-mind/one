// Settings, Privacy: the AI consent (when it was given, or "I agree" while it was not, as in first launch) and the
// pages it stands on. The core's privacy settings (Usage Stats) follow it, drawn from data.
import { useEffect, useState } from "react";
import { type Consent, getConsent, giveConsent, openPage } from "@/api/existing";
import { Button } from "@/design/ui/button";
import { firstlaunch } from "@/texts/firstlaunch";
import { formatDate } from "@/texts/format";
import { settings as texts } from "@/texts/settings";
import { useText } from "@/texts/useText";

export function Privacy() {
  const t = useText();
  const [consent, setConsent] = useState<Consent>();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void getConsent().then(({ data }) => live && data && setConsent(data));
    return () => {
      live = false;
    };
  }, []);

  async function agree() {
    if (!consent) return;
    setFailed(false);
    const given = await giveConsent(consent.text_version);
    if (given.data) setConsent({ at: given.data.at, text_version: consent.text_version });
    else setFailed(true);
  }

  const at = consent?.at;
  return (
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
        {consent && !at ? (
          <Button className="ms-auto" onClick={() => void agree()}>
            {t(firstlaunch.agree)}
          </Button>
        ) : null}
      </div>
      <p aria-live="polite" className={failed ? "text-xs font-bold" : "text-xs"}>
        {failed
          ? t(firstlaunch.consentNotSaved)
          : at
            ? t(texts.agreedOn, { date: formatDate(new Date(at), t.lang, { day: "numeric", month: "long", year: "numeric" }) })
            : consent
              ? t(texts.notAgreed)
              : null}
      </p>
    </section>
  );
}
