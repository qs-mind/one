import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const textareaVariants = cva(
  "block w-full min-w-0 resize-none field-sizing-content max-h-45 overflow-y-auto text-base text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed",
  {
    variants: {
      variant: {
        field:
          "min-h-13 rounded-xl border border-input bg-card px-4 py-3 hover:border-muted-foreground disabled:border-border disabled:bg-background disabled:text-muted-foreground aria-invalid:border-2 aria-invalid:border-foreground aria-invalid:px-[calc(--spacing(4)-1px)] aria-invalid:py-[calc(--spacing(3)-1px)]",
        bare: "min-h-11 border-0 bg-transparent px-0 py-2",
      },
    },
    defaultVariants: { variant: "field" },
  },
)

/** Six lines of 27.2px plus padding: the most a textarea grows before it scrolls inside. */
const MAX_HEIGHT = 180
const sizesItself = () =>
  typeof CSS !== "undefined" && typeof CSS.supports === "function" && CSS.supports("field-sizing", "content")

function Textarea({
  className,
  variant,
  onInput,
  ...props
}: React.ComponentProps<"textarea"> & VariantProps<typeof textareaVariants>) {
  // Where field-sizing is missing (WebKitGTK may lack it), grow by script to the same limit.
  const fallback = !sizesItself()
  return (
    <textarea
      data-slot="textarea"
      rows={fallback ? 1 : undefined}
      onInput={(event) => {
        if (fallback) {
          const box = event.currentTarget
          box.style.height = "auto"
          box.style.height = `${Math.min(box.scrollHeight, MAX_HEIGHT)}px`
        }
        onInput?.(event)
      }}
      className={cn(textareaVariants({ variant, className }))}
      {...props}
    />
  )
}

export { Textarea, textareaVariants }
