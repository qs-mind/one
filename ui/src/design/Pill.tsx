// A passive label of one look: the sample-data label on every place, a short state word. Not interactive.
import type { ComponentProps } from "react";
import { cn } from "@/design/lib/utils";

export function Pill({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="pill"
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-line px-3 text-xs whitespace-nowrap text-muted-foreground [&_svg]:size-4 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    />
  );
}
