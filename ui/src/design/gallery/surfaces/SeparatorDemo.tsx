import { Button } from "@/design/ui/button";
import { Separator } from "@/design/ui/separator";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function SeparatorDemo() {
  const t = useText();
  return (
    <Demo id="separator" title="Separator">
      <State name={t(surfaces.or)} className="flex w-full max-w-sm flex-col gap-4">
        <Button variant="outline" className="w-full">
          {t(surfaces.signInGoogle)}
        </Button>
        <div className="flex items-center gap-4">
          <Separator className="flex-1 data-horizontal:w-auto" />
          <span className="text-xs text-muted-foreground">{t(surfaces.or)}</span>
          <Separator className="flex-1 data-horizontal:w-auto" />
        </div>
        <Button variant="ghost" className="w-full">
          {t(surfaces.useKey)}
        </Button>
      </State>
      <State name="vertical" className="flex h-11 items-center gap-4">
        <span>{t(surfaces.tabSheet)}</span>
        <Separator orientation="vertical" />
        <span>{t(surfaces.tabText)}</span>
      </State>
    </Demo>
  );
}
