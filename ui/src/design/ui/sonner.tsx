"use client"

import { XIcon } from "lucide-react"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { common } from "@/texts/common"
import { useText } from "@/texts/useText"

type Props = ToasterProps & Required<Pick<ToasterProps, "theme" | "dir" | "position">>

function Toaster({ toastOptions, ...props }: Props) {
  const t = useText()
  return (
    <Sonner
      expand
      offset={{ bottom: "7rem" }}
      mobileOffset={{ bottom: "7rem" }}
      icons={{ close: <XIcon className="size-4.5" /> }}
      style={{ "--normal-bg": "var(--popover)", "--normal-text": "var(--popover-foreground)", "--normal-border": "var(--line)", "--normal-bg-hover": "var(--muted)", "--normal-border-hover": "var(--line)" } as React.CSSProperties}
      toastOptions={{
        unstyled: true,
        closeButtonAriaLabel: t(common.close),
        classNames: {
          toast: "flex w-(--width) items-center gap-3 rounded-2xl border border-line bg-popover p-4 text-base text-popover-foreground",
          content: "flex min-w-0 flex-1 flex-col gap-1",
          title: "font-normal",
          description: "text-xs text-muted-foreground",
          actionButton: "inline-flex h-11 shrink-0 items-center rounded-lg bg-primary px-5 text-base text-primary-foreground hover:bg-primary-hover active:bg-primary-pressed",
          cancelButton: "inline-flex h-11 shrink-0 items-center rounded-lg border border-line px-5 text-base text-foreground hover:bg-accent active:bg-pressed",
          closeButton: "inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-foreground hover:bg-accent active:bg-pressed",
        },
        ...toastOptions,
      }}
      {...props}
    />
  )
}

export { Toaster }
