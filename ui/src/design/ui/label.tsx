import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const labelVariants = cva("flex items-center gap-2 select-none", {
  variants: {
    size: {
      default: "text-xs text-muted-foreground",
      lg: "text-lg font-bold text-foreground",
    },
  },
  defaultVariants: { size: "default" },
})

function Label({
  className,
  size,
  ...props
}: React.ComponentProps<"label"> & VariantProps<typeof labelVariants>) {
  return (
    <label
      data-slot="label"
      className={cn(labelVariants({ size, className }))}
      {...props}
    />
  )
}

export { Label, labelVariants }
