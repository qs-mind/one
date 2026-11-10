// Label + one control + help + error, wired by Base UI's Field (ids, aria-describedby, aria-invalid), so it works
// around any Base UI control. The help-and-error holder is always mounted and polite: a pasted key's "checking…"
// and its error are announced while the engineer stays in the field (Field.Error alone has no live region).
import { Field as FieldPrimitive } from "@base-ui/react/field";
import { CircleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/design/lib/utils";
import { Label } from "@/design/ui/label";

type FieldProps = {
  label: ReactNode;
  /** Also the place for "checking…" under a pasted key. */
  help?: ReactNode;
  /** Shown when set; the core's own words where it has them. */
  error?: ReactNode;
  labelSize?: "default" | "lg";
  className?: string;
  /** One control, or one box holding a bare control (the unit box). */
  children: ReactNode;
};

export function Field({ label, help, error, labelSize = "default", className, children }: FieldProps) {
  const invalid = Boolean(error);
  return (
    <FieldPrimitive.Root invalid={invalid} className={cn("flex min-w-0 flex-col gap-2", className)}>
      <FieldPrimitive.Label render={<Label size={labelSize} />}>{label}</FieldPrimitive.Label>
      {children}
      <div aria-live="polite" className="flex flex-col gap-2 empty:-mt-2">
        {help ? (
          <FieldPrimitive.Description className="text-xs text-muted-foreground">{help}</FieldPrimitive.Description>
        ) : null}
        <FieldPrimitive.Error match={invalid} className="flex items-start gap-2 text-xs font-bold text-foreground">
          <CircleAlertIcon aria-hidden className="mt-0.5 size-4.5 shrink-0" />
          {error}
        </FieldPrimitive.Error>
      </div>
    </FieldPrimitive.Root>
  );
}
