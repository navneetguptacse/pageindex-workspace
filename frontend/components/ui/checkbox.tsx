"use client"

import * as React from "react"
import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"
import { CheckIcon, MinusIcon } from "lucide-react"
import { cn } from "cn"

function Checkbox({ className, ...props }: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer inline-flex size-icon shrink-0 items-center justify-center rounded-sm border border-input bg-card control-focus transition-colors disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive data-indeterminate:border-primary data-indeterminate:bg-primary data-indeterminate:text-primary-foreground data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="group/indicator flex items-center justify-center text-current data-ending-style:invisible"
      >
        <CheckIcon className="size-icon-xs stroke-[2.5] group-data-indeterminate/indicator:hidden" />
        <MinusIcon className="hidden size-icon-xs stroke-[2.5] group-data-indeterminate/indicator:block" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
