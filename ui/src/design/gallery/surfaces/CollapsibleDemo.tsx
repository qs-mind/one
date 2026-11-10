import { ChevronDownIcon } from "lucide-react";
import { Button } from "@/design/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/design/ui/collapsible";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function CollapsibleDemo() {
  const t = useText();
  return (
    <Demo id="collapsible" title="Collapsible">
      {[false, true].map((open) => (
        <State key={String(open)} name={t(open ? surfaces.stateOpen : surfaces.stateClosed)} className="flex max-w-md flex-col gap-2">
          <Collapsible defaultOpen={open}>
            <CollapsibleTrigger render={<Button variant="ghost" className="justify-start gap-2 px-2" />}>
              <ChevronDownIcon aria-hidden className="size-4.5 group-data-panel-open/button:rotate-180" />
              {t(surfaces.details)}
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">{t(surfaces.detailsBody)}</CollapsibleContent>
          </Collapsible>
        </State>
      ))}
    </Demo>
  );
}
