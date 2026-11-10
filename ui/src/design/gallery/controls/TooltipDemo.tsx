import { SettingsIcon } from "lucide-react";
import { Button } from "@/design/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/design/ui/tooltip";
import { common } from "@/texts/common";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

export function TooltipDemo() {
  const t = useText();
  const name = t(common.settings);
  return (
    <Demo id="tooltip" title="Tooltip">
      <State name={<Code>side=inline-end · defaultOpen</Code>} className="flex min-w-64 flex-col items-start gap-8">
        <Tooltip defaultOpen>
          <TooltipTrigger render={<Button size="icon" variant="ghost" aria-label={name} />}>
            <SettingsIcon aria-hidden />
          </TooltipTrigger>
          <TooltipContent side="inline-end">{name}</TooltipContent>
        </Tooltip>
      </State>
      <State name={`${t(foundation.hover)} · ${t(foundation.focus)}`}>
        <Tooltip>
          <TooltipTrigger render={<Button variant="outline" />}>{t(common.send)}</TooltipTrigger>
          <TooltipContent>{t(common.send)}</TooltipContent>
        </Tooltip>
      </State>
    </Demo>
  );
}
