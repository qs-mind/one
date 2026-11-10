// The live line: one line from the last data-progress of the running reply ("who · what"), still dot beside it, and
// the work log behind it. A screen reader hears the line only when the worker changes, never on each page count.
import { CheckIcon, CircleIcon } from "lucide-react";
import { useRef } from "react";
import { MetaLine } from "@/design/MetaLine";
import { StatusDot } from "@/design/StatusDot";
import { Button } from "@/design/ui/button";
import { Popover, PopoverContent, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/design/ui/popover";
import { ScrollArea } from "@/design/ui/scroll-area";
import { conversation } from "@/texts/conversation";
import { useText } from "@/texts/useText";
import { Task, TaskContent, TaskItem, TaskTrigger } from "./ai/task";
import type { ProgressData, Text } from "./parts";

/** One step of the work log: who, what, and whether it has ended. */
export type LogStep = { agent: Text; text: Text; done: boolean };

/** Steps in a row by the same worker, under that worker's name. */
function groups(log: readonly LogStep[]): { agent: Text; steps: LogStep[] }[] {
  const out: { agent: Text; steps: LogStep[] }[] = [];
  for (const step of log) {
    const last = out.at(-1);
    if (last && last.agent.en === step.agent.en) last.steps.push(step);
    else out.push({ agent: step.agent, steps: [step] });
  }
  return out;
}

type LiveLineProps = { progress: ProgressData | null; log?: readonly LogStep[] };

/** The words a screen reader hears: set when the worker changes, kept while only the count moves. */
function useAnnouncement(progress: ProgressData | null, say: (p: ProgressData) => string): string {
  const held = useRef<{ agent: string; words: string } | null>(null);
  if (!progress) return "";
  const agent = progress.agent.en;
  if (held.current?.agent !== agent) held.current = { agent, words: say(progress) };
  return held.current.words;
}

export function LiveLine({ progress, log = [] }: LiveLineProps) {
  const t = useText();
  const announcement = useAnnouncement(progress, (p) => `${t(p.agent)}: ${t(p.text)}`);
  if (!progress) return null;
  return (
    <div>
      <Popover>
        <PopoverTrigger
          render={
            <Button
              variant="ghost"
              wrap
              className="justify-start gap-3 px-1 text-start text-xs text-muted-foreground hover:text-foreground active:text-foreground"
            />
          }
        >
          <StatusDot state="now" />
          <MetaLine items={[t(progress.agent), t(progress.text)]} />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-112 max-w-[calc(100vw-2rem)]">
          <PopoverHeader>
            <PopoverTitle className="font-bold">{t(conversation.workLog)}</PopoverTitle>
          </PopoverHeader>
          <ScrollArea className="max-h-90">
            {log.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t(conversation.logEmpty)}</p>
            ) : (
              <div className="flex flex-col gap-2">
                {groups(log).map((group, index) => (
                  // Groups have no id of their own; their order is their identity.
                  <Task key={index}>
                    <TaskTrigger title={t(group.agent)} />
                    <TaskContent>
                      {group.steps.map((step, at) => (
                        <TaskItem key={at} className="flex items-start gap-2">
                          {step.done ? (
                            <CheckIcon aria-label={t(conversation.stepDone)} className="mt-1 size-4 shrink-0" />
                          ) : (
                            <CircleIcon aria-label={t(conversation.stepRunning)} className="mt-1 size-4 shrink-0" />
                          )}
                          <span>{t(step.text)}</span>
                        </TaskItem>
                      ))}
                    </TaskContent>
                  </Task>
                ))}
              </div>
            )}
          </ScrollArea>
        </PopoverContent>
      </Popover>
      <span role="status" className="sr-only">
        {announcement}
      </span>
    </div>
  );
}
