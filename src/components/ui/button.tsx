import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-normal tracking-wide ring-offset-background transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 active:scale-[0.98]",
  {
    variants: {
      variant: {
        // The app's primary: beige with the glass highlight and a soft glow on hover (materials.css .btn-glow).
        default: "btn-glow bg-beige text-cream hover:bg-beige/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        // Secondary: the light glass of a selected nav pill.
        outline: "glass-nav text-foreground hover:bg-white/40 dark:hover:bg-white/10",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-secondary hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        // Same primary as `default`: kept as a name so existing call sites do not change.
        hero: "btn-glow bg-beige text-cream hover:bg-beige/90",
        // A quiet text action beside a primary ("Cancelar", "Ver todo"): no fill, color change only.
        quiet: "rounded-md text-muted-foreground hover:text-foreground",
        // A red text action ("Colgar", "Eliminar"): no fill until hovered. Filled red is `destructive`.
        dangerGhost: "text-destructive hover:bg-destructive/10",
        recording: "bg-destructive text-destructive-foreground",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-full px-3.5",
        lg: "h-11 rounded-full px-6 text-sm",
        xl: "h-12 rounded-full px-8 text-[15px] font-normal",
        text: "h-7 gap-1.5 px-2 text-[13px]",
        icon: "h-10 w-10",
        "icon-lg": "h-12 w-12",
        "icon-xl": "h-16 w-16",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
