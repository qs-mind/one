// The frame of every gallery demo: a section named by its code name (Latin), and one labelled sample per state.
import type { ReactNode } from "react";
import { SectionLabel } from "@/design/SectionLabel";

export function Demo({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section data-demo={id} aria-labelledby={`demo-${id}`} className="flex flex-col gap-3">
      <SectionLabel id={`demo-${id}`}>
        <bdi lang="en" dir="ltr">
          {title}
        </bdi>
      </SectionLabel>
      <div className="flex flex-wrap items-start gap-6">{children}</div>
    </section>
  );
}

export function State({ name, children, className }: { name: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={className ?? "flex min-w-0 flex-col gap-2"}>
      <span className="text-xs text-muted-foreground">{name}</span>
      {children}
    </div>
  );
}

/** A code name (a variant, a size, a token) inside a state name: Latin, kept in one piece. */
export function Code({ children }: { children: ReactNode }) {
  return (
    <bdi lang="en" dir="ltr">
      {children}
    </bdi>
  );
}
