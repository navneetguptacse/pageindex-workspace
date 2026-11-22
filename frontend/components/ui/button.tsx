import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const buttonVariants = cva(
  "group/button inline-flex min-w-0 shrink-0 items-center justify-center gap-2 rounded-control border border-transparent text-sm/5 font-medium whitespace-nowrap control-focus transition-colors select-none [--button-icon-size:var(--spacing-icon)] disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:size-(--button-icon-size) [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary-hover",
        outline:
          "border-border bg-card hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary aria-expanded:text-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_5%)] aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary aria-expanded:text-foreground",
        destructive:
          "bg-destructive-surface text-destructive hover:bg-destructive-hover",
        citation:
          "border-border bg-accent text-accent-foreground hover:border-primary",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-control px-3",
        inline: "min-h-0 border-0 p-0",
        xs: "min-h-control-xs gap-1.5 px-2 text-xs/4 [--button-icon-size:var(--spacing-icon-xs)]",
        sm: "min-h-control-sm px-2.5",
        lg: "min-h-control-lg px-4 [--button-icon-size:var(--spacing-icon-lg)]",
        icon: "size-control",
        "icon-xs":
          "size-control-xs [--button-icon-size:var(--spacing-icon-xs)]",
        "icon-sm": "size-control-sm",
        "icon-lg":
          "size-control-lg [--button-icon-size:var(--spacing-icon-lg)]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  nativeButton,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  const isCustomRender = props.render !== undefined
  return (
    <ButtonPrimitive
      data-slot="button"
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      nativeButton={nativeButton !== undefined ? nativeButton : !isCustomRender}
      {...props}
    />
  )
}

export { Button, buttonVariants }
