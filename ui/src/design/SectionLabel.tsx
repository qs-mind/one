// The label over a section: 15px, 400, muted. A heading by default.
import type { ReactNode } from "react";
import { cn } from "@/design/lib/utils";

type SectionLabelProps = { as?: "h2" | "h3" | "div"; id?: string; className?: string; children: ReactNode };

export function SectionLabel({ as: Tag = "h2", id, className, children }: SectionLabelProps) {
  return (
    <Tag id={id} className={cn("text-xs font-normal text-muted-foreground", className)}>
      {children}
    </Tag>
  );
}
