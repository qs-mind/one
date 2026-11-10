import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"
import { cn } from "cn"
import { CheckIcon } from "lucide-react"

function Checkbox({ className, ...props }: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative flex size-5 shrink-0 items-center justify-center rounded-sm border-[1.5px] border-muted-foreground bg-card group-has-[:focus-visible]/field-label:not-data-checked:border-muted-foreground after:absolute after:-inset-3 disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-disabled data-disabled:data-checked:border-line data-disabled:data-checked:bg-disabled data-disabled:data-checked:text-muted-foreground aria-invalid:border-2 aria-invalid:border-foreground aria-invalid:aria-checked:border-primary data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground group-has-[:focus-visible]/field-label:data-checked:border-primary",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current transition-none [&>svg]:size-3.5"
      >
        <CheckIcon
        />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
