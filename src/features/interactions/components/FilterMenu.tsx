import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export type FilterChoice = { value: string; label: string };

/**
 * One filter as a glass chip that opens its choices ("Todas ▾"). The first choice is the "all"
 * one: it sits apart, and the chip reads quieter while it is picked.
 */
export function FilterMenu({
  label,
  value,
  choices,
  onChange,
}: {
  /** What is being filtered, for screen readers ("Canal"). */
  label: string;
  value: string;
  choices: FilterChoice[];
  onChange: (next: string) => void;
}) {
  const [all, ...rest] = choices;
  const current = choices.find((choice) => choice.value === value) ?? all;
  const narrowed = current?.value !== all?.value;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`${label}: ${current?.label ?? ""}`}
          className={cn(THEME_TOKENS.interaction.menuChip, "max-w-[14rem]", !narrowed && "text-muted-foreground")}
        >
          <span className="truncate">{current?.label}</span>
          <ChevronDown aria-hidden className="h-3.5 w-3.5 shrink-0 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-72 overflow-y-auto">
        <DropdownMenuRadioGroup value={current?.value} onValueChange={onChange}>
          {all ? <DropdownMenuRadioItem value={all.value}>{all.label}</DropdownMenuRadioItem> : null}
          {rest.length ? <DropdownMenuSeparator /> : null}
          {rest.map((choice) => (
            <DropdownMenuRadioItem key={choice.value} value={choice.value}>
              {choice.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
