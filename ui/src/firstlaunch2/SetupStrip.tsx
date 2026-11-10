// The setup strip under first launch: one progress bar for everything ONE downloads beyond the installer
// (GET /setup/parts, kept current by the `setup` event). Offline it says what waits for the internet; a part that
// failed or cannot run here says what will not work and why, with Try again for a failed one. Everything else
// works meanwhile. When every part is present it shows nothing.
import { useEffect, useState } from "react";
import { subscribeGeneral } from "@/activity";
import { client, type Schemas } from "@/api/client";
import { Button } from "@/design/ui/button";
import { Progress, ProgressLabel, ProgressValue } from "@/design/ui/progress";
import { firstlaunch } from "@/texts/firstlaunch";
import { intlLocale } from "@/texts/format";
import { useText } from "@/texts/useText";

type Part = Schemas["SetupPart"];
const GETTING: Part["state"][] = ["queued", "downloading", "waiting_network"];
const megabytes = (bytes: number) => Math.round(bytes / 1_000_000);

export function SetupStrip() {
  const t = useText();
  const [setup, setSetup] = useState<Schemas["SetupState"]>();
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    let live = true;
    const load = () =>
      void client
        .GET("/setup/parts")
        .then(({ data }) => live && data && setSetup(data))
        .catch(() => undefined);
    // Listen first, then load: nothing said meanwhile is missed, and a stream that comes back loads again.
    const stop = subscribeGeneral((event) => event.type === "setup" && live && setSetup(event.setup), load);
    load();
    return () => {
      live = false;
      stop();
    };
  }, []);

  if (!setup) return null;
  const getting = setup.parts.filter((part) => GETTING.includes(part.state));
  const broken = setup.parts.filter((part) => part.state === "failed" || part.state === "unavailable");
  if (getting.length === 0 && broken.length === 0) return null;

  // The bar counts what is or will be on this computer; a broken part is said below it instead.
  const counted = setup.parts.filter((part) => part.state === "present" || GETTING.includes(part.state));
  const done = counted.reduce((sum, part) => sum + part.done_bytes, 0);
  const total = counted.reduce((sum, part) => sum + part.total_bytes, 0);
  const downloading = getting.find((part) => part.state === "downloading");
  const waiting = getting.filter((part) => part.state === "waiting_network");
  const names = new Intl.ListFormat(intlLocale(t.lang), { type: "conjunction" });
  const label = downloading
    ? t(firstlaunch.setupGetting, { part: t(downloading.title) })
    : waiting.length > 0
      ? t(firstlaunch.setupOffline, { parts: names.format(waiting.map((part) => t(part.title))) })
      : t(firstlaunch.setupWaitsTurn);
  const count = t(firstlaunch.megabytes, { done: megabytes(done), total: megabytes(total) });

  async function retry() {
    setRetrying(true);
    const { data } = await client.POST("/setup/parts/retry").catch(() => ({ data: undefined }));
    setRetrying(false);
    if (data) setSetup(data);
  }

  return (
    <div className="flex flex-col gap-4">
      {getting.length > 0 ? (
        <Progress value={total > 0 ? Math.round((done / total) * 100) : null} getAriaValueText={() => count}>
          <ProgressLabel>{label}</ProgressLabel>
          <ProgressValue>{() => count}</ProgressValue>
        </Progress>
      ) : null}
      {broken.map((part) => (
        <div key={part.id} className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <p className="flex min-w-0 flex-1 flex-col">
            <span className="text-xs font-bold">{t(firstlaunch.notAvailable, { affects: t(part.affects) })}</span>
            {part.reason ? <span className="text-xs text-muted-foreground">{t(part.reason)}</span> : null}
          </p>
          {part.state === "failed" ? (
            <Button variant="outline" loading={retrying} onClick={() => void retry()}>
              {t(firstlaunch.tryAgain)}
            </Button>
          ) : null}
        </div>
      ))}
    </div>
  );
}
