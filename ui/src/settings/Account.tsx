// My profile, the QS Mind account (contract S221): who is signed in, and Sign out; or Sign in, which the core opens
// in the browser while the screen asks GET /account every second until it ends. No answer here holds a token.
import { useEffect, useState } from "react";
import { type Account as AccountState, cancelSignIn, getAccount, signIn } from "@/api/existing";
import { signOut } from "@/api/settingsKept";
import { Button } from "@/design/ui/button";
import { firstlaunch } from "@/texts/firstlaunch";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

/** How often the screen asks whether the sign-in has ended. */
export const POLL_MS = 1000;

export function Account() {
  const t = useText();
  const [account, setAccount] = useState<AccountState>();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<TextPair>();
  const waiting = account?.state === "waiting";

  useEffect(() => {
    let live = true;
    void getAccount().then(({ data }) => live && data && setAccount(data));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(() => {
      void getAccount().then(({ data }) => {
        if (!data || data.state === "waiting") return;
        if (data.state === "signed_out") setProblem(data.note ?? firstlaunch.signInFailed);
        setAccount(data);
      });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [waiting]);

  async function start() {
    setProblem(undefined);
    setBusy(true);
    const started = await signIn(t.lang);
    setBusy(false);
    if (!started.data) return setProblem(started.error ?? firstlaunch.signInFailed);
    setAccount({ ...started.data, state: started.data.state === "signed_in" ? "signed_in" : "waiting" });
  }

  async function leave() {
    setProblem(undefined);
    setBusy(true);
    const answer = await signOut();
    setBusy(false);
    if (answer.data) setAccount({ state: "signed_out" });
    else setProblem(answer.error ?? texts.notSignedOut);
  }

  async function cancel() {
    await cancelSignIn();
    setAccount({ state: "signed_out" });
  }

  return (
    <section aria-labelledby="account" className="flex flex-col gap-3">
      <h2 id="account" className="text-lg font-bold">
        {t(texts.account)}
      </h2>
      <p className="text-muted-foreground">{t(texts.accountWhy)}</p>
      {account === undefined ? (
        <div aria-busy="true" className="min-h-11" />
      ) : account.state === "signed_in" ? (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <p className="min-w-0 flex-1">{t(firstlaunch.signedIn, { email: account.email ?? account.name ?? "" })}</p>
          <Button variant="outline" loading={busy} onClick={() => void leave()}>
            {t(texts.signOut)}
          </Button>
        </div>
      ) : waiting ? (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <p className="min-w-0 flex-1">{t(firstlaunch.signingIn)}</p>
          <Button variant="outline" onClick={() => void cancel()}>
            {t(firstlaunch.cancel)}
          </Button>
        </div>
      ) : (
        <Button variant="outline" className="self-start" loading={busy} onClick={() => void start()}>
          {t(texts.signIn)}
        </Button>
      )}
      <p aria-live="polite" className="text-xs font-bold empty:hidden">
        {problem ? t(problem) : null}
      </p>
    </section>
  );
}
