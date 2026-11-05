// Popover over Radix, shadcn-style: our tokens, logical sides, no blur. `inline` keeps the content inside the
// trigger's own DOM instead of a portal, for popovers that sit inside a scaled canvas frame.
import * as Radix from "@radix-ui/react-popover";
import type { ComponentProps } from "react";

export const Popover = Radix.Root;
export const PopoverTrigger = Radix.Trigger;
export const PopoverAnchor = Radix.Anchor;
export const PopoverClose = Radix.Close;

export function PopoverContent({
  className = "",
  align = "start",
  sideOffset = 8,
  inline = false,
  ...props
}: ComponentProps<typeof Radix.Content> & { inline?: boolean }) {
  const content = (
    <Radix.Content
      align={align}
      sideOffset={sideOffset}
      className={`z-50 max-w-sm rounded-[14px] border border-ink/[0.08] bg-paper p-4 text-ink shadow-[0_4px_16px_rgb(14_15_18/0.08)] outline-none ${className}`}
      {...props}
    />
  );
  return inline ? content : <Radix.Portal>{content}</Radix.Portal>;
}
