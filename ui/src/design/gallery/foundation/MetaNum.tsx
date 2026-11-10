import { MetaLine } from "@/design/MetaLine";
import { Num } from "@/design/Num";
import { foundation } from "@/texts/design/foundation";
import { formatDate } from "@/texts/format";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

export function MetaNum() {
  const t = useText();
  return (
    <Demo id="meta-num" title="MetaLine · Num">
      <State name={<Code>MetaLine</Code>}>
        <MetaLine
          className="text-xs text-muted-foreground"
          items={["Lead QS", t(foundation.files, { n: 14 }), null, t(foundation.submission, { date: formatDate(new Date(2026, 10, 21), t.lang) })]}
        />
      </State>
      <State name={<Code>Num value</Code>}>
        <span className="flex flex-wrap gap-6">
          <Num value={-1800} />
          <Num value={2203200} />
          <Num value={0.46} options={{ style: "percent" }} />
        </span>
      </State>
      <State name={<Code>Num children</Code>}>
        <span className="flex flex-wrap gap-6">
          <Num>7/03</Num>
          <Num>{t(foundation.cubicMetre)}</Num>
        </span>
      </State>
    </Demo>
  );
}
