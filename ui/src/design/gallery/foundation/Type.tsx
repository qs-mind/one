import { MetaLine } from "@/design/MetaLine";
import { cn } from "@/design/lib/utils";
import { foundation } from "@/texts/design/foundation";
import { text, useText } from "@/texts/useText";
import { Code, Demo } from "../parts";

const STEPS = [
  { name: "small · text-xs · 15/24", className: "text-xs" },
  { name: "data · .dense text-base · 16/24", className: "text-base", dense: true },
  { name: "body · text-base · 17/27.2", className: "text-base" },
  { name: "lead · text-lg · 19/30.4", className: "text-lg" },
  { name: "figure · text-xl 700 · 22/35.2", className: "text-xl font-bold" },
  { name: "title · text-2xl 700 · 26/41.6", className: "text-2xl font-bold" },
  { name: "display · text-3xl 700 · 34/54.4", className: "text-3xl font-bold" },
] as const;

export function Type() {
  const t = useText();
  return (
    <Demo id="type" title="Type">
      <div className="flex w-full flex-col gap-4">
        {STEPS.map((step) => (
          <div key={step.name} className="flex flex-col">
            <span className="text-xs text-muted-foreground">
              <Code>{step.name}</Code>
            </span>
            <p className={cn("flex flex-wrap gap-x-6", "dense" in step && "dense", step.className)}>
              <span lang="ar" dir="rtl">
                {text(foundation.typeSample, "ar")}
              </span>
              <span lang="en" dir="ltr">
                {text(foundation.typeSample, "en")}
              </span>
            </p>
          </div>
        ))}
        <div className="flex flex-col">
          <span className="text-xs text-muted-foreground">
            <Code>MetaLine</Code>
          </span>
          <MetaLine className="text-xs text-muted-foreground" items={["Lead QS", t(foundation.files, { n: 14 })]} />
        </div>
      </div>
    </Demo>
  );
}
