import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const variants = cva(
  "group/button inline-flex shrink-0 items-center justify-center border border-transparent bg-clip-padding text-base font-normal select-none data-disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4.5",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-pressed data-disabled:bg-disabled data-disabled:text-muted-foreground",
        outline:
          "border-line bg-transparent text-foreground hover:bg-accent active:bg-pressed aria-expanded:bg-accent data-disabled:border-border data-disabled:text-muted-foreground",
        ghost:
          "bg-transparent text-foreground hover:bg-accent active:bg-pressed aria-expanded:bg-accent data-disabled:text-muted-foreground",
        link: "link text-foreground data-disabled:text-muted-foreground data-disabled:no-underline",
      },
      size: {
        default: "min-h-11 gap-2 rounded-lg px-5",
        lg: "min-h-13 gap-2 rounded-xl px-8",
        icon: "size-11 rounded-lg",
      },
      wrap: {
        false: "whitespace-nowrap",
        // 7 + 27.2 + 7 + the 2px edge: one line is exactly the 44 (or 52) of min-h, more lines grow.
        true: "whitespace-normal py-[calc(--spacing(2)-1px)] text-center",
      },
    },
    compoundVariants: [
      { wrap: false, size: "default", class: "h-11" },
      { wrap: false, size: "lg", class: "h-13" },
      { variant: "link", class: "h-auto min-h-11 rounded-none border-0 px-0" },
    ],
    defaultVariants: { variant: "default", size: "default", wrap: false },
  },
)

// cva only joins; cn lets the compound variants and the caller's className win (link: px-0 over px-5).
// Callers that put buttonVariants() on an <a> get the merged string too.
function buttonVariants(props?: Parameters<typeof variants>[0]) {
  return cn(variants(props))
}

function Button({
  className,
  variant = "default",
  size = "default",
  wrap = false,
  loading = false,
  disabled,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants> & { loading?: boolean }) {
  return (
    <ButtonPrimitive
      data-slot="button"
      disabled={disabled || loading}
      focusableWhenDisabled={loading || undefined}
      aria-busy={loading || undefined}
      className={buttonVariants({ variant, size, wrap, className })}
      {...props}
    />
  )
}

export { Button, buttonVariants }
