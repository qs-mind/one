// A tender with no plan (S58, S63): it says so, and one action asks the Lead to write it (POST .../plan/request).
// Once asked, the button gives way to a line; the plan arrives with its `plan` event and the card replaces this.
import { useState } from "react";
import type { Schemas } from "@/api/client";
import { notify } from "@/design/notify";
import { Button } from "@/design/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/design/ui/card";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";

type NoPlanProps = {
  /** Asks the Lead; resolves with the core's words when it refused, null when the work started. */
  onRequest: () => Promise<Schemas["Text"] | null>;
  /** Why the Lead cannot work now (TenderRow.blocked): the button is off and the reason shows. */
  blocked: Schemas["LeadBlock"] | null;
};

export function NoPlan({ onRequest, blocked }: NoPlanProps) {
  const t = useText();
  const [asked, setAsked] = useState<"no" | "asking" | "yes">("no");
  const ask = async () => {
    setAsked("asking");
    // a request that got no answer did not reach the Lead: the button stays
    const refused = await onRequest().catch(() => texts.failed);
    setAsked(refused ? "no" : "yes");
    if (refused) notify(t(refused));
  };
  return (
    <Card data-noplan className="mx-auto w-full max-w-(--measure)">
      <CardHeader>
        <CardTitle>{t(texts.noPlanTitle)}</CardTitle>
        <CardDescription>{t(texts.noPlanBody)}</CardDescription>
      </CardHeader>
      {blocked && (
        <CardContent>
          <p>{t(blocked.reason)}</p>
        </CardContent>
      )}
      <CardFooter>
        {asked === "yes" ? (
          <p role="status" className="text-muted-foreground">
            {t(texts.planAsked)}
          </p>
        ) : (
          <Button wrap disabled={asked === "asking" || blocked !== null} onClick={() => void ask()}>
            {t(texts.askForPlan)}
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}
