// ai-elements `task`, on U1's Base UI collapsible: a trigger that renders a 44px ghost row, a panel with a start-side
// rule (border-s, so it sits on the right in Arabic), no enter or leave motion.
import { ChevronDownIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/design/lib/utils";
import { Button } from "@/design/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/design/ui/collapsible";

export type TaskItemFileProps = ComponentProps<"span">;

export const TaskItemFile = ({ children, className, ...props }: TaskItemFileProps) => (
  <span
    className={cn("inline-flex items-center gap-1 rounded-lg border border-line px-2 text-xs text-foreground", className)}
    {...props}
  >
    {children}
  </span>
);

export type TaskItemProps = ComponentProps<"div">;

export const TaskItem = ({ children, className, ...props }: TaskItemProps) => (
  <div className={cn("text-xs text-muted-foreground", className)} {...props}>
    {children}
  </div>
);

export type TaskProps = ComponentProps<typeof Collapsible>;

export const Task = ({ defaultOpen = true, className, ...props }: TaskProps) => (
  <Collapsible className={cn(className)} defaultOpen={defaultOpen} {...props} />
);

export type TaskTriggerProps = Omit<ComponentProps<typeof CollapsibleTrigger>, "title"> & {
  title: ReactNode;
  icon?: ReactNode;
};

export const TaskTrigger = ({ className, title, icon, ...props }: TaskTriggerProps) => (
  <CollapsibleTrigger
    className={cn("group/task", className)}
    render={
      <Button
        variant="ghost"
        wrap
        className="w-full justify-start gap-2 px-1 text-start text-xs text-muted-foreground hover:text-foreground"
      />
    }
    {...props}
  >
    {icon}
    <span className="min-w-0 flex-1">{title}</span>
    <ChevronDownIcon aria-hidden className="size-4 group-data-panel-open/task:rotate-180" />
  </CollapsibleTrigger>
);

export type TaskContentProps = ComponentProps<typeof CollapsibleContent>;

export const TaskContent = ({ children, className, ...props }: TaskContentProps) => (
  <CollapsibleContent className={cn("text-popover-foreground", className)} {...props}>
    <div className="mt-2 flex flex-col gap-2 border-s-2 border-line ps-4">{children}</div>
  </CollapsibleContent>
);
