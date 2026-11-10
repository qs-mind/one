import { useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/design/lib/utils";
import { stateFill } from "@/design/now-waiting";
import { useTheme } from "@/design/theme";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Code, Demo } from "../parts";
import { describeColour, TOKENS, type TokenRow } from "./tokenList";

/** Copper is reached through now-waiting.tsx only, so "now" and "waiting" take its fill class. */
const COPPER: Record<string, string> = { now: stateFill.now, waiting: stateFill.waiting };

function Swatch({ token, theme }: { token: TokenRow; theme: string }) {
  const t = useText();
  const swatch = useRef<HTMLSpanElement>(null);
  const [value, setValue] = useState("");
  useLayoutEffect(() => {
    if (swatch.current) setValue(describeColour(getComputedStyle(swatch.current).backgroundColor));
  }, [theme]);
  const copper = COPPER[token.name];
  return (
    <li className="flex min-w-0 items-center gap-3">
      <span
        ref={swatch}
        aria-hidden
        className={cn("size-11 shrink-0 rounded-lg border border-border", copper)}
        style={copper ? undefined : { backgroundColor: `var(--${token.name})` }}
      />
      <span className="flex min-w-0 flex-col">
        <Code>--{token.name}</Code>
        <span className="text-xs text-muted-foreground">
          <Code>
            {token.inLight} / {token.inDark}
          </Code>
        </span>
        <span className="text-xs text-muted-foreground">
          {t(foundation.valueHere)}: <Code>{value}</Code>
        </span>
      </span>
    </li>
  );
}

export function Colours() {
  const { resolved } = useTheme();
  return (
    <Demo id="colours" title="Colours">
      <ul className="grid w-full grid-cols-[repeat(auto-fill,minmax(17rem,1fr))] gap-x-6 gap-y-4">
        {TOKENS.map((token) => (
          <Swatch key={token.name} token={token} theme={resolved} />
        ))}
      </ul>
    </Demo>
  );
}
