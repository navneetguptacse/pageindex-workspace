import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const textareaVariants = cva(
  "field-sizing-content w-full min-w-0 resize-none text-sm/5",
  {
    variants: {
      variant: {
        default: "min-h-24 control-field px-3 py-2",
        code: "min-h-44 control-field px-3 py-2 font-mono text-xs/5",
        composer:
          "max-h-40 min-h-13 bg-transparent px-2 py-1.5 outline-none placeholder:text-muted-foreground disabled:opacity-50",
      },
    },
    defaultVariants: { variant: "default" },
  }
)

function Textarea({
  className,
  variant,
  rows = 3,
  ...props
}: React.ComponentProps<"textarea"> & VariantProps<typeof textareaVariants>) {
  return (
    <textarea
      data-slot="textarea"
      data-appearance={variant === "composer" ? "grouped" : "standalone"}
      className={cn(textareaVariants({ variant }), className)}
      rows={rows}
      {...props}
    />
  )
}

export { Textarea }
