import { Button } from "@/design/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/design/ui/card";
import { WaitingLabel } from "@/design/now-waiting";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function CardDemo() {
  const t = useText();
  return (
    <Demo id="card" title="Card">
      <State name={`outline · ${t(surfaces.stateRest)}`} className="flex w-full max-w-md flex-col gap-2">
        <Card>
          <CardHeader>
            <CardTitle>{t(surfaces.planTitle)}</CardTitle>
            <CardAction className="text-xs text-muted-foreground">{t(surfaces.planDays, { n: 12 })}</CardAction>
          </CardHeader>
          <CardContent>{t(surfaces.planBody)}</CardContent>
          <CardFooter>
            <Button>{t(surfaces.agree)}</Button>
            <Button variant="outline">{t(surfaces.discussPlan)}</Button>
          </CardFooter>
        </Card>
      </State>
      <State name="panel" className="flex w-full max-w-md flex-col gap-2">
        <Card variant="panel">
          <CardHeader>
            <CardTitle>{t(surfaces.sourceTitle)}</CardTitle>
            <CardDescription>{t(surfaces.sourceBody)}</CardDescription>
          </CardHeader>
        </Card>
      </State>
      <State name="panel · sm" className="flex w-full max-w-md flex-col gap-2">
        <Card variant="panel" size="sm">
          <CardContent className="flex flex-col gap-2">
            <WaitingLabel>{t(surfaces.waitingLine)}</WaitingLabel>
            <span>{t(surfaces.approvePlan)}</span>
          </CardContent>
          <CardFooter>
            <Button>{t(surfaces.agree)}</Button>
          </CardFooter>
        </Card>
      </State>
      <State name="outline · sm" className="flex w-full max-w-md flex-col gap-2">
        <Card size="sm">
          <CardHeader>
            <CardTitle>{t(surfaces.providerTitle)}</CardTitle>
            <CardDescription>{t(surfaces.providerMeta)}</CardDescription>
          </CardHeader>
          <CardFooter>
            <Button variant="outline">{t(surfaces.discussPlan)}</Button>
          </CardFooter>
        </Card>
      </State>
    </Demo>
  );
}
