import { Search, X } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** Search the list by the name of the person the conversation was with; sits beside the filter chips. */
export function InteractionSearch({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  return (
    <div className="glass-nav relative inline-flex h-8 w-full items-center rounded-full text-[13px] focus-within:ring-2 focus-within:ring-ring sm:w-52">
      <Search aria-hidden className="pointer-events-none absolute left-3 h-3.5 w-3.5 text-muted-foreground" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && value) onChange("");
        }}
        placeholder={copy.searchPlaceholder}
        aria-label={copy.searchLabel}
        maxLength={100}
        className={cn(
          "h-full w-full rounded-full bg-transparent pl-8 pr-8 text-foreground placeholder:text-muted-foreground",
          "focus:outline-none [&::-webkit-search-cancel-button]:hidden",
        )}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={copy.searchClear}
          className="absolute right-2 flex h-5 w-5 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X aria-hidden className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  );
}
