import * as React from "react";
import * as TogglePrimitive from "@radix-ui/react-toggle";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * `chip` is the one on/off pill (a filter, a field to include, a language to keep): outlined when
 * off, a beige tint and text when on. Pass `aria-pressed` state through `pressed`.
 */
const toggleVariants = cva(
  "inline-flex items-center justify-center gap-1.5 text-sm ring-offset-background transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "rounded-md bg-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground data-[state=on]:bg-secondary data-[state=on]:text-foreground",
        chip: "rounded-full border border-border/60 bg-card text-muted-foreground hover:bg-secondary/60 hover:text-foreground data-[state=on]:border-beige/40 data-[state=on]:bg-beige/10 data-[state=on]:text-beige",
      },
      size: {
        default: "h-10 px-3",
        sm: "h-8 px-3 text-[13px]",
        lg: "h-11 px-5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

const Toggle = React.forwardRef<
  React.ElementRef<typeof TogglePrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof TogglePrimitive.Root> & VariantProps<typeof toggleVariants>
>(({ className, variant, size, ...props }, ref) => (
  <TogglePrimitive.Root ref={ref} className={cn(toggleVariants({ variant, size, className }))} {...props} />
));

Toggle.displayName = TogglePrimitive.Root.displayName;

export { Toggle, toggleVariants };
