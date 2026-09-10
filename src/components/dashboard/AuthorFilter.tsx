import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { ActivityAuthor } from "@/lib/activity-authors";
import { cn } from "@/lib/utils";

export function AuthorFilter({
  authors,
  value,
  onChange,
  currentUserId,
}: {
  authors: ActivityAuthor[];
  value: string | null;
  onChange: (userId: string | null) => void;
  currentUserId?: string | null;
}) {
  if (authors.length < 2) return null;

  const chip = (id: string | null, label: string) => {
    const selected = value === id;
    return (
      <button
        key={id ?? "all"}
        type="button"
        onClick={() => onChange(id)}
        className={cn(
          THEME_TOKENS.interaction.navPill,
          selected
            ? THEME_TOKENS.interaction.navPillActive
            : THEME_TOKENS.interaction.navPillIdle,
        )}
      >
        {label}
      </button>
    );
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {chip(null, "All")}
      {authors.map((author) =>
        chip(
          author.userId,
          author.userId === currentUserId ? "You" : author.label,
        ),
      )}
    </div>
  );
}
