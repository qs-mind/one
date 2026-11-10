// ai-elements `sources`, on U1's Base UI collapsible. The words ("{n} sources") come from the caller; a source is a
// link-looking button by default (ONE opens a source in its own viewer, never in a browser tab).
import { BookIcon, ChevronDownIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/design/lib/utils";
import { Button, buttonVariants } from "@/design/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/design/ui/collapsible";

export type SourcesProps = ComponentProps<typeof Collapsible>;

export const Sources = ({ className, ...props }: SourcesProps) => (
  <Collapsible className={cn("text-xs text-foreground", className)} {...props} />
);

export type SourcesTriggerProps = ComponentProps<typeof CollapsibleTrigger> & { label: ReactNode };

export const SourcesTrigger = ({ className, label, ...props }: SourcesTriggerProps) => (
  <CollapsibleTrigger
    className={cn("group/sources", className)}
    render={<Button variant="ghost" className="justify-start gap-2 px-1 text-xs" />}
    {...props}
  >
    {label}
    <ChevronDownIcon aria-hidden className="size-4 group-data-panel-open/sources:rotate-180" />
  </CollapsibleTrigger>
);

export type SourcesContentProps = ComponentProps<typeof CollapsibleContent>;

export const SourcesContent = ({ className, ...props }: SourcesContentProps) => (
  <CollapsibleContent className={cn("flex w-fit flex-col", className)} {...props} />
);

export type SourceProps = Omit<ComponentProps<"button">, "title"> & { title: ReactNode };

export const Source = ({ title, children, className, ...props }: SourceProps) => (
  <button
    type="button"
    className={buttonVariants({ variant: "link", className: cn("justify-start gap-2 text-xs", className) })}
    {...props}
  >
    {children ?? (
      <>
        <BookIcon aria-hidden className="size-4" />
        <span>{title}</span>
      </>
    )}
  </button>
);
