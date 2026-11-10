// Direction for Base UI (arrow keys, logical sides), tooltips and notices. It does not set dir, lang or data-theme:
// the language and theme stores put those on <html>, because portals render under <body> and ignore a wrapper.
import type { ReactNode } from "react";
import { DirectionProvider } from "@/design/ui/direction";
import { Toaster } from "@/design/ui/sonner";
import { TooltipProvider } from "@/design/ui/tooltip";
import { useTheme } from "@/design/theme";
import { common } from "@/texts/common";
import { useLang } from "@/texts/language";
import { useText } from "@/texts/useText";

export function AppProviders({ children }: { children: ReactNode }) {
  const { dir } = useLang();
  const { resolved } = useTheme();
  const t = useText();
  return (
    <DirectionProvider direction={dir}>
      <TooltipProvider delay={400}>
        {children}
        <Toaster dir={dir} theme={resolved} position="bottom-center" customAriaLabel={t(common.notifications)} />
      </TooltipProvider>
    </DirectionProvider>
  );
}
