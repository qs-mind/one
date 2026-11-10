import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const inputVariants = cva(
  "w-full min-w-0 text-base text-foreground placeholder:text-muted-foreground data-disabled:cursor-not-allowed",
  {
    variants: {
      variant: {
        field:
          "h-13 rounded-xl border border-input bg-card px-4 hover:border-muted-foreground data-disabled:border-border data-disabled:bg-background data-disabled:text-muted-foreground aria-invalid:border-2 aria-invalid:border-foreground aria-invalid:px-[calc(--spacing(4)-1px)]",
        bare: "h-11 border-0 bg-transparent px-0",
      },
    },
    defaultVariants: { variant: "field" },
  },
)

function Input({
  className,
  type,
  variant,
  ...props
}: React.ComponentProps<"input"> & VariantProps<typeof inputVariants>) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(inputVariants({ variant, className }))}
      {...props}
    />
  )
}

export { Input, inputVariants }
