import { ChevronDown } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { ActivityAuthor } from "@/lib/activity-authors";
import {
  activityFilterChips,
  shouldShowActivityAuthorFilter,
} from "@/lib/activity-authors";
import { cn } from "@/lib/utils";

export function AuthorFilter({
  authors,
  value,
  onChange,
  currentUserId,
  canViewCompany = true,
  compact = false,
}: {
  authors: ActivityAuthor[];
  value: string | null;
  onChange: (userId: string | null) => void;
  currentUserId?: string | null;
  canViewCompany?: boolean;
  compact?: boolean;
}) {
  const { t } = useLanguage();
  if (!shouldShowActivityAuthorFilter(Boolean(canViewCompany), currentUserId)) {
    return null;
  }
  const labelOf = (label: string) => {
    if (label === "Mine") return t.product.activityMine;
    if (label === "All") return t.product.activityAll;
    return label;
  };

  return (
    <label className="inline-flex items-center gap-2">
      <span className={THEME_TOKENS.typography.capsLabel}>{t.product.activityShow}</span>
      <span className="relative inline-flex">
        <select
          aria-label={t.product.activityShow}
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value || null)}
          className={cn(
            "appearance-none rounded-full border border-border/40 bg-secondary/5 text-foreground cursor-pointer focus:outline-none",
            compact
              ? "h-8 min-w-[7.5rem] max-w-[12rem] pl-3 pr-8 text-[13px]"
              : "h-10 min-w-[9rem] max-w-[14rem] pl-4 pr-10 text-sm",
          )}
        >
          {activityFilterChips(authors, currentUserId).map((chip) => (
            <option key={chip.id ?? "all"} value={chip.id ?? ""}>
              {labelOf(chip.label)}
            </option>
          ))}
        </select>
        <ChevronDown
          className={cn(
            "pointer-events-none absolute top-1/2 -translate-y-1/2 text-muted-foreground/40",
            compact ? "right-2 h-3.5 w-3.5" : "right-3 h-4 w-4",
          )}
        />
      </span>
    </label>
  );
}
