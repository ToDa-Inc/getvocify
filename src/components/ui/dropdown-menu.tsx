import * as React from "react";
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { Check, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { MENU_TOKENS } from "@/lib/theme/tokens";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const DropdownMenu = DropdownMenuPrimitive.Root;

const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;

const DropdownMenuGroup = DropdownMenuPrimitive.Group;

const DropdownMenuPortal = DropdownMenuPrimitive.Portal;

const DropdownMenuSub = DropdownMenuPrimitive.Sub;

const DropdownMenuRadioGroup = DropdownMenuPrimitive.RadioGroup;

const DropdownMenuSubTrigger = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.SubTrigger>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.SubTrigger> & {
    inset?: boolean;
  }
>(({ className, inset, children, ...props }, ref) => (
  <DropdownMenuPrimitive.SubTrigger
    ref={ref}
    className={cn(MENU_TOKENS.item, "data-[state=open]:bg-secondary/70", inset && "pl-8", className)}
    {...props}
  >
    {children}
    <ChevronRight className="ml-auto" />
  </DropdownMenuPrimitive.SubTrigger>
));
DropdownMenuSubTrigger.displayName = DropdownMenuPrimitive.SubTrigger.displayName;

const DropdownMenuSubContent = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.SubContent>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.SubContent>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.SubContent ref={ref} className={cn(MENU_TOKENS.surface, className)} {...props} />
));
DropdownMenuSubContent.displayName = DropdownMenuPrimitive.SubContent.displayName;

const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>
>(({ className, sideOffset = 6, collisionPadding = 12, ...props }, ref) => (
  <DropdownMenuPrimitive.Portal>
    <DropdownMenuPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      collisionPadding={collisionPadding}
      className={cn(MENU_TOKENS.surface, className)}
      {...props}
    />
  </DropdownMenuPrimitive.Portal>
));
DropdownMenuContent.displayName = DropdownMenuPrimitive.Content.displayName;

const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> & {
    inset?: boolean;
    /** `danger`: sign out, delete. Red text on a faint red tint, never on the brand fill. */
    tone?: "default" | "danger";
  }
>(({ className, inset, tone = "default", ...props }, ref) => (
  <DropdownMenuPrimitive.Item
    ref={ref}
    className={cn(MENU_TOKENS.item, tone === "danger" && MENU_TOKENS.itemDanger, inset && "pl-8", className)}
    {...props}
  />
));
DropdownMenuItem.displayName = DropdownMenuPrimitive.Item.displayName;

const DropdownMenuCheckboxItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.CheckboxItem>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.CheckboxItem>
>(({ className, children, checked, ...props }, ref) => (
  <DropdownMenuPrimitive.CheckboxItem
    ref={ref}
    className={cn(MENU_TOKENS.item, MENU_TOKENS.itemSelectable, className)}
    checked={checked}
    {...props}
  >
    {children}
    <span className={MENU_TOKENS.check}>
      <DropdownMenuPrimitive.ItemIndicator>
        <Check />
      </DropdownMenuPrimitive.ItemIndicator>
    </span>
  </DropdownMenuPrimitive.CheckboxItem>
));
DropdownMenuCheckboxItem.displayName = DropdownMenuPrimitive.CheckboxItem.displayName;

const DropdownMenuRadioItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.RadioItem>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.RadioItem>
>(({ className, children, ...props }, ref) => (
  <DropdownMenuPrimitive.RadioItem
    ref={ref}
    className={cn(MENU_TOKENS.item, MENU_TOKENS.itemSelectable, className)}
    {...props}
  >
    {children}
    <span className={MENU_TOKENS.check}>
      <DropdownMenuPrimitive.ItemIndicator>
        <Check />
      </DropdownMenuPrimitive.ItemIndicator>
    </span>
  </DropdownMenuPrimitive.RadioItem>
));
DropdownMenuRadioItem.displayName = DropdownMenuPrimitive.RadioItem.displayName;

export type DropdownMenuSegment = {
  value: string;
  /** Accessible name, and the tooltip when the segment shows an icon or a short code. */
  label: string;
  icon?: React.ReactNode;
  /** Visible text when shorter than the label ("ES" for Español). */
  short?: string;
};

/**
 * A setting with 2–4 values inside a menu (Tema, Idioma): one row, a glass thumb slides to the chosen
 * value. Each segment is a real menuitemradio, so arrow keys reach it and choosing keeps the menu open.
 */
function DropdownMenuSegmented({
  label,
  value,
  onValueChange,
  options,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: DropdownMenuSegment[];
}) {
  const index = Math.max(0, options.findIndex((option) => option.value === value));
  return (
    <div className="flex items-center justify-between gap-3 py-1 pl-2.5 pr-1">
      <span className="text-[13px] text-muted-foreground">{label}</span>
      <DropdownMenuPrimitive.RadioGroup
        value={value}
        onValueChange={onValueChange}
        aria-label={label}
        className="relative grid rounded-full border border-border/60 bg-secondary/40 p-0.5"
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        <span
          aria-hidden
          className="glass-nav pointer-events-none absolute inset-y-0.5 left-0.5 rounded-full transition-transform duration-200 ease-silk motion-reduce:transition-none"
          style={{ width: `calc((100% - 4px) / ${options.length})`, transform: `translateX(${index * 100}%)` }}
        />
        {options.map((option) => {
          const shown = option.icon ?? option.short ?? option.label;
          const segment = (
            <DropdownMenuPrimitive.RadioItem
              key={option.value}
              value={option.value}
              aria-label={option.label}
              onSelect={(event) => event.preventDefault()}
              className="relative z-10 flex h-7 min-w-8 cursor-default select-none items-center justify-center rounded-full px-2 text-xs text-muted-foreground outline-none transition-colors duration-150 data-[highlighted]:text-foreground data-[state=checked]:text-foreground data-[highlighted]:data-[state=unchecked]:bg-foreground/[0.05] motion-reduce:transition-none [&_svg]:size-3.5"
            >
              {shown}
            </DropdownMenuPrimitive.RadioItem>
          );
          if (shown === option.label) return segment;
          return (
            <Tooltip key={option.value}>
              <TooltipTrigger asChild>{segment}</TooltipTrigger>
              <TooltipContent side="top">{option.label}</TooltipContent>
            </Tooltip>
          );
        })}
      </DropdownMenuPrimitive.RadioGroup>
    </div>
  );
}

const DropdownMenuLabel = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label> & {
    inset?: boolean;
  }
>(({ className, inset, ...props }, ref) => (
  <DropdownMenuPrimitive.Label ref={ref} className={cn(MENU_TOKENS.label, inset && "pl-8", className)} {...props} />
));
DropdownMenuLabel.displayName = DropdownMenuPrimitive.Label.displayName;

const DropdownMenuSeparator = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.Separator ref={ref} className={cn(MENU_TOKENS.separator, className)} {...props} />
));
DropdownMenuSeparator.displayName = DropdownMenuPrimitive.Separator.displayName;

const DropdownMenuShortcut = ({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) => {
  return <span className={cn("ml-auto text-xs tracking-widest text-muted-foreground", className)} {...props} />;
};
DropdownMenuShortcut.displayName = "DropdownMenuShortcut";

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioItem,
  DropdownMenuSegmented,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuGroup,
  DropdownMenuPortal,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuRadioGroup,
};
