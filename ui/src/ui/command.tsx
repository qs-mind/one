// The command palette's list over cmdk, shadcn-style, with our tokens. `CommandDialog` puts it in the Radix dialog.
import { Command as Cmdk } from "cmdk";
import type { ComponentProps, ReactNode } from "react";
import { Dialog, DialogContent, DialogTitle } from "./dialog";

export function Command({ className = "", ...props }: ComponentProps<typeof Cmdk>) {
  return <Cmdk className={`flex flex-col overflow-hidden ${className}`} {...props} />;
}

export function CommandDialog({
  title,
  open,
  onOpenChange,
  children,
}: {
  title: string;
  open: boolean;
  onOpenChange(open: boolean): void;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined}>
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <Command label={title}>{children}</Command>
      </DialogContent>
    </Dialog>
  );
}

export function CommandInput({ className = "", ...props }: ComponentProps<typeof Cmdk.Input>) {
  return (
    <Cmdk.Input
      dir="auto" // typed text sets its own side; the empty field keeps the page's, so the placeholder sits right in Arabic
      className={`border-b border-ink/10 bg-transparent px-4 py-3 outline-none placeholder:text-slate [&:placeholder-shown]:[direction:inherit] ${className}`}
      {...props}
    />
  );
}

export function CommandList({ className = "", ...props }: ComponentProps<typeof Cmdk.List>) {
  return <Cmdk.List className={`max-h-[50vh] overflow-y-auto p-2 ${className}`} {...props} />;
}

export function CommandEmpty({ className = "", ...props }: ComponentProps<typeof Cmdk.Empty>) {
  return <Cmdk.Empty className={`px-3 py-6 text-center text-slate ${className}`} {...props} />;
}

export function CommandGroup({ className = "", ...props }: ComponentProps<typeof Cmdk.Group>) {
  return (
    <Cmdk.Group
      className={`[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-slate ${className}`}
      {...props}
    />
  );
}

export function CommandItem({ className = "", ...props }: ComponentProps<typeof Cmdk.Item>) {
  return (
    <Cmdk.Item
      className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 data-[selected=true]:bg-stone ${className}`}
      {...props}
    />
  );
}
