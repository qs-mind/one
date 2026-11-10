// "Sign in with QS Mind and I fill in the name" (step 2). The core opens the browser at the account; the screen asks
// GET /account every second until the sign-in ends (contract S210), then hands the account on so the form can take
// the name. Sign-in stays optional: a failed one says so, and the form below works without it.
import { useEffect, useState } from "react";
import { type Account, cancelSignIn, getAccount, signIn } from "@/api/existing";
import { Button } from "@/design/ui/button";
import { firstlaunch } from "@/texts/firstlaunch";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

/** How often the screen asks whether the sign-in has ended. */
export const POLL_MS = 1000;

export function SignIn({ onSignedIn }: { onSignedIn: (account: Account) => void }) {
  const t = useText();
  const [account, setAccount] = useState<Account>();
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState<TextPair>();
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
        if (data.state === "signed_out") setFailed(data.note ?? firstlaunch.signInFailed);
        if (data.state === "signed_in") onSignedIn(data);
        setAccount(data);
      });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [waiting, onSignedIn]);

  async function start() {
    setFailed(undefined);
    setStarting(true);
    const started = await signIn(t.lang);
    setStarting(false);
    if (!started.data) return setFailed(started.error ?? firstlaunch.signInFailed);
    if (started.data.state === "signed_in") onSignedIn(started.data);
    setAccount({ ...started.data, state: started.data.state === "signed_in" ? "signed_in" : "waiting" });
  }

  async function cancel() {
    await cancelSignIn();
    setAccount({ state: "signed_out" });
  }

  if (account?.state === "signed_in")
    return (
      <p className="text-base">
        {t(firstlaunch.signedIn, { email: account.email ?? account.name ?? "" })}
      </p>
    );

  return (
    <div className="flex flex-col gap-3">
      {waiting ? (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <p className="min-w-0 flex-1">{t(firstlaunch.signingIn)}</p>
          <Button variant="outline" onClick={() => void cancel()}>
            {t(firstlaunch.cancel)}
          </Button>
        </div>
      ) : (
        <Button variant="outline" size="lg" wrap loading={starting} onClick={() => void start()}>
          {t(firstlaunch.signIn)}
        </Button>
      )}
      <p aria-live="polite" className="text-xs font-bold empty:hidden">
        {failed ? t(failed) : null}
      </p>
    </div>
  );
}
