import { ScrollArea } from "@/design/ui/scroll-area";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

const STEPS = Array.from({ length: 16 }, (_, i) => i + 1);

export function ScrollAreaDemo() {
  const t = useText();
  return (
    <Demo id="scroll-area" title="ScrollArea">
      <State name={t(surfaces.workLog)} className="flex w-80 flex-col gap-2">
        <ScrollArea className="h-56 rounded-2xl border border-line">
          <ol className="flex flex-col gap-2 p-4 text-xs">
            {STEPS.map((n) => (
              <li key={n}>{t(surfaces.logStep, { n, page: n * 4 })}</li>
            ))}
          </ol>
        </ScrollArea>
      </State>
    </Demo>
  );
}
