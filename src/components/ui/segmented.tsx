import * as React from "react";
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";

import { cn } from "@/lib/utils";
import { THEME_TOKENS } from "@/lib/theme/tokens";

export type SegmentedOption<T extends string> = {
  value: T;
  label: React.ReactNode;
  disabled?: boolean;
  /** Accessible name when `label` is only an icon. */
  "aria-label"?: string;
};

type SegmentedProps<T extends string> = {
  value: T;
  onValueChange: (value: T) => void;
  options: readonly SegmentedOption<T>[];
  "aria-label": string;
  className?: string;
};

/**
 * Pick one of 2–4 values of the same setting (billing interval, role, access): the compact glass
 * pill row the Interacciones / Equipo tabs use. For switching views of one page use `Tabs`.
 */
export function Segmented<T extends string>({ value, onValueChange, options, className, ...rest }: SegmentedProps<T>) {
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      value={value}
      // A single group reports "" when the active item is pressed again; a setting always has a value.
      onValueChange={(next) => next && onValueChange(next as T)}
      aria-label={rest["aria-label"]}
      className={cn(THEME_TOKENS.interaction.segmentList, "inline-flex flex-nowrap", className)}
    >
      {options.map((option) => (
        <ToggleGroupPrimitive.Item
          key={option.value}
          value={option.value}
          disabled={option.disabled}
          aria-label={option["aria-label"]}
          className={cn(THEME_TOKENS.interaction.segmentTab, "inline-flex items-center gap-1.5 whitespace-nowrap disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
        >
          {option.label}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
}
