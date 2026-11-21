import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cn } from "cn"

function Input({
  className,
  type,
  appearance = "standalone",
  ...props
}: React.ComponentProps<"input"> & { appearance?: "standalone" | "grouped" }) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      data-appearance={appearance}
      className={cn(
        "w-full min-w-0 px-3 text-sm/5",
        appearance === "standalone"
          ? "h-control control-field"
          : "h-full bg-transparent ps-0 outline-none placeholder:text-muted-foreground disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Input }
