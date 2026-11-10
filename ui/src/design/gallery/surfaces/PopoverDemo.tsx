import { Button } from "@/design/ui/button";
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/design/ui/popover";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function PopoverDemo() {
  const t = useText();
  return (
    <Demo id="popover" title="Popover">
      {(["bottom", "inline-end"] as const).map((side) => (
        <State key={side} name={side}>
          <Popover>
            <PopoverTrigger render={<Button variant="outline" />}>{t(surfaces.workLog)}</PopoverTrigger>
            <PopoverContent side={side}>
              <PopoverHeader>
                <PopoverTitle>{t(surfaces.workLogTitle)}</PopoverTitle>
                <PopoverDescription>{t(surfaces.workLogBody)}</PopoverDescription>
              </PopoverHeader>
            </PopoverContent>
          </Popover>
        </State>
      ))}
    </Demo>
  );
}
