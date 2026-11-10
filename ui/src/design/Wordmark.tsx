// The typed wordmark: always "ONE", never translated. The only place with weight 600 and letter spacing.
import { cn } from "@/design/lib/utils";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span lang="en" dir="ltr" className={cn("text-xs font-[600] tracking-[1px] text-foreground", className)}>
      ONE
    </span>
  );
}
