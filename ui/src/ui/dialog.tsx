// Dialog over Radix, shadcn-style: our tokens, no blur behind it (WebKitGTK), focus kept inside and returned on close.
import * as Radix from "@radix-ui/react-dialog";
import type { ComponentProps } from "react";

export const Dialog = Radix.Root;
export const DialogTrigger = Radix.Trigger;
export const DialogClose = Radix.Close;

export function DialogContent({ className = "", children, ...props }: ComponentProps<typeof Radix.Content>) {
  return (
    <Radix.Portal>
      <Radix.Overlay className="fixed inset-0 z-50 bg-ink/30" />
      <Radix.Content
        className={`fixed inset-x-0 top-[12vh] z-50 mx-auto w-[min(40rem,calc(100vw-2rem))] rounded-[14px] border border-ink/10 bg-paper text-ink shadow-lg shadow-ink/12 outline-none ${className}`}
        {...props}
      >
        {children}
      </Radix.Content>
    </Radix.Portal>
  );
}

export function DialogTitle({ className = "", ...props }: ComponentProps<typeof Radix.Title>) {
  return <Radix.Title className={`font-semibold ${className}`} {...props} />;
}

export function DialogDescription({ className = "", ...props }: ComponentProps<typeof Radix.Description>) {
  return <Radix.Description className={`text-slate ${className}`} {...props} />;
}
