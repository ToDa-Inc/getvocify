import { ChevronDown } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { ActivityAuthor } from "@/lib/activity-authors";
import {
  activityFilterChips,
  shouldShowActivityAuthorFilter,
} from "@/lib/activity-authors";

export function AuthorFilter({
  authors,
  value,
  onChange,
  currentUserId,
  canViewCompany = true,
}: {
  authors: ActivityAuthor[];
  value: string | null;
  onChange: (userId: string | null) => void;
  currentUserId?: string | null;
  canViewCompany?: boolean;
}) {
  if (!shouldShowActivityAuthorFilter(Boolean(canViewCompany), currentUserId)) {
    return null;
  }

  return (
    <label className="inline-flex items-center gap-2">
      <span className={THEME_TOKENS.typography.capsLabel}>Show</span>
      <span className="relative inline-flex">
        <select
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value || null)}
          className="h-10 min-w-[9rem] max-w-[14rem] appearance-none rounded-full border border-border/40 bg-secondary/5 pl-4 pr-10 text-sm text-foreground cursor-pointer focus:outline-none"
        >
          {activityFilterChips(authors, currentUserId).map((chip) => (
            <option key={chip.id ?? "all"} value={chip.id ?? ""}>
              {chip.label}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/40" />
      </span>
    </label>
  );
}
