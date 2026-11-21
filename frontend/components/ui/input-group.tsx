import type { ComponentProps } from "react"
import { cn } from "cn"

export function InputGroup({
  className,
  variant = "inline",
  ...props
}: ComponentProps<"div"> & { variant?: "inline" | "composer" }) {
  return (
    <div
      data-slot="input-group"
      data-variant={variant}
      className={cn(
        "flex min-w-0 items-center gap-2 rounded-control border border-input bg-card transition-colors has-[[data-appearance=grouped]:enabled]:hover:border-muted-foreground has-[[data-appearance=grouped]:focus-visible]:border-ring has-[[data-appearance=grouped]:focus-visible]:outline-2 has-[[data-appearance=grouped]:focus-visible]:outline-offset-2 has-[[data-appearance=grouped]:focus-visible]:outline-ring has-[[data-appearance=grouped][aria-invalid=true]]:border-destructive",
        variant === "composer"
          ? "items-end rounded-surface p-1.5"
          : "h-control",
        className
      )}
      {...props}
    />
  )
}

export function InputGroupAddon({
  className,
  ...props
}: ComponentProps<"span">) {
  return (
    <span
      data-slot="input-group-addon"
      className={cn(
        "pointer-events-none inline-flex shrink-0 items-center ps-3 text-muted-foreground [&>svg]:size-icon",
        className
      )}
      {...props}
    />
  )
}
