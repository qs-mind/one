import { ArrowUpIcon, XIcon } from "lucide-react";
import { Button } from "@/design/ui/button";
import { common } from "@/texts/common";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

const VARIANTS = ["default", "outline", "ghost", "link"] as const;
const FORCED = ["hover", "pressed", "focus"] as const;

function VariantRow({ variant }: { variant: (typeof VARIANTS)[number] }) {
  const t = useText();
  const label = t(controls.agree);
  return (
    <div className="flex w-full flex-wrap items-end gap-6">
      <State name={<Code>{variant}</Code>}>
        <Button variant={variant}>{label}</Button>
      </State>
      {FORCED.map((state) => (
        <State key={state} name={t(foundation[state])}>
          <Button variant={variant} data-force={state}>
            {label}
          </Button>
        </State>
      ))}
      <State name={t(foundation.disabled)}>
        <Button variant={variant} disabled>
          {label}
        </Button>
      </State>
      <State name={t(foundation.loading)}>
        <Button variant={variant} loading>
          {t(controls.checking)}
        </Button>
      </State>
    </div>
  );
}

export function ButtonDemo() {
  const t = useText();
  return (
    <Demo id="button" title="Button">
      {VARIANTS.map((variant) => (
        <VariantRow key={variant} variant={variant} />
      ))}
      <div className="flex w-full flex-wrap items-end gap-6">
        <State name={<Code>size=lg</Code>}>
          <Button size="lg">{t(controls.agree)}</Button>
        </State>
        <State name={<Code>size=lg outline w-full</Code>} className="flex w-80 flex-col gap-2">
          <Button size="lg" variant="outline" className="w-full">
            {t(surfaces.signInGoogle)}
          </Button>
        </State>
        <State name={<Code>size=icon</Code>}>
          <span className="flex gap-3">
            <Button size="icon" aria-label={t(common.send)}>
              <ArrowUpIcon aria-hidden />
            </Button>
            <Button size="icon" variant="ghost" aria-label={t(common.close)}>
              <XIcon aria-hidden />
            </Button>
            <Button size="icon" variant="ghost" data-force="hover" aria-label={t(common.close)}>
              <XIcon aria-hidden />
            </Button>
          </span>
        </State>
        <State name={t(foundation.wraps)} className="flex w-70 flex-col gap-2">
          <Button wrap className="w-full">
            {t(controls.longDecision)}
          </Button>
          <Button wrap variant="outline" className="w-full">
            {t(controls.discuss)}
          </Button>
        </State>
      </div>
    </Demo>
  );
}
