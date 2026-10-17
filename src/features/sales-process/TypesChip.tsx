import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLanguage } from "@/lib/i18n";
import { typesSummary } from "@/lib/sales-process";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * Which interaction types a person runs, as a chip that is its own control (like the role chip it replaces): a menu of the
 * company's types with a tick each. Nothing ticked, or everything, is "Todas".
 */
export function TypesChip({
  value,
  types,
  disabled,
  label,
  onChange,
}: {
  value: string[] | null;
  types: { key: string; label: string }[];
  disabled?: boolean;
  label: string;
  /** null = every type. */
  onChange: (next: string[] | null) => void;
}) {
  const { t } = useLanguage();
  const c = t.product.pb2.process;
  const chosen = new Set(value ?? []);
  const toggle = (key: string, on: boolean) => {
    const next = types.map((item) => item.key).filter((k) => (k === key ? on : chosen.has(k)));
    onChange(next.length && next.length < types.length ? next : null);
  };
  const summary = typesSummary(value, types, c.teamAll, t.product.pb2.process.teamMany);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={`${label}: ${summary}`} disabled={disabled || !types.length} className={THEME_TOKENS.interaction.menuChip}>
          <span className="max-w-[12rem] truncate">{summary}</span>
          <ChevronDown aria-hidden className="h-3 w-3 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-w-xs">
        <p className="px-2 py-1.5 text-[11px] leading-snug text-muted-foreground">{c.teamHint}</p>
        <DropdownMenuSeparator />
        {types.map((item) => (
          <DropdownMenuCheckboxItem
            key={item.key}
            checked={value === null || chosen.has(item.key)}
            onSelect={(event) => event.preventDefault()}
            onCheckedChange={(on) => toggle(item.key, on)}
          >
            {item.label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
