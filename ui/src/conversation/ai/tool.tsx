// ai-elements `tool`, restyled: the state is a Pill (no Badge, no colour per state: the icon and the word say it),
// the input and output are plain left-to-right text (no code-block, no shiki), and every word comes from the caller.
import type { ToolUIPart } from "ai";
import { CheckIcon, ChevronDownIcon, CircleIcon, ClockIcon, WrenchIcon, XIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { isValidElement } from "react";
import { Pill } from "@/design/Pill";
import { cn } from "@/design/lib/utils";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/design/ui/collapsible";

export type ToolProps = ComponentProps<typeof Collapsible>;

export const Tool = ({ className, ...props }: ToolProps) => (
  <Collapsible className={cn("w-full rounded-2xl border border-line", className)} {...props} />
);

export type ToolState = ToolUIPart["state"];

const icons: Record<ToolState, ReactNode> = {
  "input-streaming": <CircleIcon aria-hidden />,
  "input-available": <ClockIcon aria-hidden />,
  "approval-requested": <ClockIcon aria-hidden />,
  "approval-responded": <CheckIcon aria-hidden />,
  "output-available": <CheckIcon aria-hidden />,
  "output-error": <XIcon aria-hidden />,
  "output-denied": <XIcon aria-hidden />,
};

export type ToolHeaderProps = {
  title: ReactNode;
  state: ToolState;
  /** The state in words, in the screen's language. */
  stateLabel: string;
  className?: string;
};

export const ToolHeader = ({ className, title, state, stateLabel, ...props }: ToolHeaderProps) => (
  <CollapsibleTrigger
    className={cn("group/tool flex min-h-11 w-full items-center justify-between gap-4 px-4 py-2 text-start", className)}
    {...props}
  >
    <span className="flex min-w-0 flex-wrap items-center gap-2">
      <WrenchIcon aria-hidden className="size-4 text-muted-foreground" />
      <span className="font-bold">{title}</span>
      <Pill>
        {icons[state]}
        {stateLabel}
      </Pill>
    </span>
    <ChevronDownIcon aria-hidden className="size-4 text-muted-foreground group-data-panel-open/tool:rotate-180" />
  </CollapsibleTrigger>
);

export type ToolContentProps = ComponentProps<typeof CollapsibleContent>;

export const ToolContent = ({ className, ...props }: ToolContentProps) => (
  <CollapsibleContent className={cn("text-popover-foreground", className)} {...props} />
);

/** Data as the tool gave it: left to right, kept in one block that scrolls sideways inside itself. */
const Plain = ({ value }: { value: unknown }) => (
  <pre dir="ltr" className="overflow-x-auto rounded-xl bg-muted p-3 text-xs whitespace-pre-wrap">
    {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
  </pre>
);

export type ToolInputProps = ComponentProps<"div"> & { input: ToolUIPart["input"]; label: string };

export const ToolInput = ({ className, input, label, ...props }: ToolInputProps) => (
  <div className={cn("flex flex-col gap-2 overflow-hidden px-4 pb-4", className)} {...props}>
    <p className="text-xs text-muted-foreground">{label}</p>
    <Plain value={input} />
  </div>
);

export type ToolOutputProps = ComponentProps<"div"> & {
  output: ToolUIPart["output"];
  errorText: ToolUIPart["errorText"];
  label: string;
};

export const ToolOutput = ({ className, output, errorText, label, ...props }: ToolOutputProps) => {
  if (!(output || errorText)) return null;
  return (
    <div className={cn("flex flex-col gap-2 px-4 pb-4", className)} {...props}>
      <p className="text-xs text-muted-foreground">{label}</p>
      {errorText && <p className="font-bold">{errorText}</p>}
      {output !== undefined && (isValidElement(output) ? output : <Plain value={output} />)}
    </div>
  );
};
