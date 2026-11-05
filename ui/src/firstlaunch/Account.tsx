// The QS Mind account step: why (it keeps the Backup key, so a new computer gets the projects back; free, optional),
// then "Sign in with QS Mind". The core opens the browser itself at the account, which goes straight on when the
// browser is signed in already, and to Google when it is not; the screen waits, asking GET /account until the sign-in
// ends. The link is shown too, as text to copy, for when no browser opens: the page opens no link itself there.
// "Sign in on another device" asks the core for a device code instead: its page opens in any browser, so in a plain
// browser (ONE seen from another computer) it is a real link, in a new tab.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, inInstalledApp } from "../api";
import { coreLine, send } from "../core";
import { fill, language, pick, t, type Text, texts, useLanguage } from "../i18n";
import { Feedback, type Nav, primary, quiet, StepScreen } from "./parts";

/** A button on the waiting box's Stone: Paper with a quiet frame (the usual Stone button would not show there). */
const onStone =
  "rounded-md border border-ink/15 bg-paper px-5 py-2.5 text-ink transition-colors duration-150 ease-out hover:bg-ink/[0.04] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink";

type Account = {
  state: "signed_out" | "waiting" | "signed_in";
  email?: string;
  name?: string;
  device?: { user_code: string; verification_uri: string };
  /** Why the last sign-in failed, in the core's words. */
  note?: Text;
};

/** How often the screen asks whether the sign-in has ended. */
export const POLL_MS = 1000;

async function read(): Promise<Account | undefined> {
  const response = await api("/account").catch(() => undefined);
  return response?.ok ? ((await response.json().catch(() => undefined)) as Account | undefined) : undefined;
}

/** The screen is open in a browser on another computer than the core's (through a tunnel, say): the core's browser
 * opens there, not here. */
function seenFromElsewhere(): boolean {
  return !inInstalledApp() && !/^(127\.|localhost$|\[::1\]$)/.test(window.location.hostname);
}

export function Account({ nav }: { nav: Nav }) {
  useLanguage();
  const [account, setAccount] = useState<Account>({ state: "signed_out" });
  const [url, setUrl] = useState<string>();
  const [opening, setOpening] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const waiting = account.state === "waiting";
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    void read().then((now) => live.current && now && setAccount(now)); // before Task 5's core, signed out
    return () => {
      live.current = false;
    };
  }, []);

  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(() => {
      void read().then((now) => {
        if (!live.current || !now) return;
        if (now.state === "signed_out") setFailed(now.note ?? texts.accountFailed); // refused, expired or stopped in the core
        setAccount(now);
      });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [waiting]);

  const signIn = useCallback(async (device: boolean) => {
    setFailed(undefined);
    setUrl(undefined);
    setOpening(true);
    const response = await send("/account/sign-in", "POST", { locale: language(), device });
    if (!live.current) return;
    setOpening(false);
    if (!response?.ok) return setFailed(await coreLine(response, texts.accountFailed));
    const answer = (await response.json().catch(() => ({}))) as Account & { url?: string };
    setUrl(answer.url);
    setAccount({ state: "waiting", device: answer.device });
  }, []);

  async function cancel() {
    await send("/account/cancel", "POST");
    setAccount({ state: "signed_out" });
    setUrl(undefined);
  }

  const signedIn = account.state === "signed_in";
  return (
    <StepScreen
      title={t("accountTitle")}
      help={t("accountWhy")}
      nav={nav}
      skip={!signedIn}
      onSkip={() => void (waiting ? cancel() : Promise.resolve()).then(() => nav.pass("skipped"))}
      failed={failed && pick(failed)}
      next={
        signedIn && (
          <button type="button" onClick={() => void nav.pass("done")} className={`${primary} fl-rise`}>
            {t("setupNext")}
          </button>
        )
      }
    >
      {signedIn && <Feedback state="done">{fill(t("accountSignedInAs"), { email: account.email ?? account.name ?? "" })}</Feedback>}
      {account.state === "signed_out" && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={opening} onClick={() => void signIn(false)} className={primary}>
              {t("accountSignIn")}
            </button>
            <button type="button" disabled={opening} onClick={() => void signIn(true)} className={quiet}>
              {t("accountUseDevice")}
            </button>
          </div>
          {opening ? <Feedback state="busy">{t("accountOpening")}</Feedback> : <p className="text-sm text-slate">{t("accountSignInHow")}</p>}
        </div>
      )}
      {waiting && (
        <div className="fl-rise flex flex-col gap-4 rounded-lg bg-stone px-5 py-4">
          {account.device ? (
            <>
              <p>
                <DeviceLine uri={account.device.verification_uri} href={url ?? account.device.verification_uri} />
              </p>
              <code dir="ltr" className="self-start rounded-md bg-paper px-4 py-2 font-mono text-2xl tracking-[0.3em] select-all">
                {account.device.user_code}
              </code>
              <Feedback state="busy">{t("accountDeviceWaiting")}</Feedback>
            </>
          ) : (
            <>
              <Feedback state="busy">{t("accountWaiting")}</Feedback>
              {seenFromElsewhere() ? (
                <p className="text-slate">{t("accountElsewhere")}</p>
              ) : (
                url && (
                  <div className="flex flex-col gap-2">
                    <p className="text-slate">{t("accountNoBrowser")}</p>
                    <code dir="ltr" className="rounded-md bg-paper px-3 py-2 text-sm break-all select-all">
                      {url}
                    </code>
                  </div>
                )
              )}
            </>
          )}
          <div>
            <button type="button" onClick={() => void cancel()} className={onStone}>
              {t("accountCancel")}
            </button>
          </div>
        </div>
      )}
    </StepScreen>
  );
}

/** "On your phone or any computer, open {uri} and type this code:", with the address kept left to right inside
 * Arabic. In a plain browser it is a link that opens the device page in a new tab, the code already in it; in the
 * installed app the core has opened it already, and it is text to read off. */
function DeviceLine({ uri, href }: { uri: string; href: string }) {
  const [before, after] = t("accountDevice").split("{uri}");
  const shown = uri.replace(/^https:\/\//, "");
  return (
    <>
      {before}
      <bdi dir="ltr" className="font-medium text-ink select-all">
        {inInstalledApp() ? (
          shown
        ) : (
          <a href={href} target="_blank" rel="noopener" className="underline decoration-slate/40 underline-offset-4 hover:decoration-ink">
            {shown}
          </a>
        )}
      </bdi>
      {after}
    </>
  );
}
