import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { toast } from "sonner";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { glossaryApi, glossaryKeys, type GlossaryItem } from "@/lib/api/glossary";

// A stable default: a fresh [] on every render would change the query data identity while it loads.
const NO_ITEMS: GlossaryItem[] = [];

/** Words split on commas and new lines, so pasting a list adds them all. */
function splitWords(text: string): string[] {
  return [...new Set(text.split(/[,\n]/).map((w) => w.trim()).filter(Boolean))];
}

/**
 * The glossary as tags (Granola's "Personal jargon"): type a word and press Enter, paste a list to add
 * several. The sound-alikes are made by the backend when a word is added.
 */
export const UserGlossary = ({ readOnly = false }: { readOnly?: boolean }) => {
  const queryClient = useQueryClient();
  const { data: items = NO_ITEMS, isLoading } = useQuery({
    queryKey: glossaryKeys.list(),
    queryFn: () => glossaryApi.getGlossary(),
    staleTime: Infinity,
  });
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: glossaryKeys.list() });

  const add = async () => {
    const known = new Set(items.map((i) => i.target_word.toLowerCase()));
    const words = splitWords(draft).filter((w) => !known.has(w.toLowerCase()));
    if (words.length === 0) {
      setDraft("");
      return;
    }
    setAdding(true);
    try {
      if (words.length === 1) {
        await glossaryApi.addItem({ target_word: words[0], phonetic_hints: [], category: "General", boost_factor: 5 });
      } else {
        await glossaryApi.bulkAdd(words.map((w) => ({ target_word: w, phonetic_hints: [], category: "General" })));
      }
      setDraft("");
      await refresh();
    } catch {
      toast.error("Could not add to the glossary");
    } finally {
      setAdding(false);
    }
  };

  const remove = async (item: GlossaryItem) => {
    if (!item.id) return;
    setRemovingId(item.id);
    try {
      await glossaryApi.deleteItem(item.id);
      await refresh();
    } catch {
      toast.error("Could not remove the word");
    } finally {
      setRemovingId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <VocifySpinner size={16} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm text-foreground">Glossary</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {readOnly
            ? "Names and terms your calls say, set by an admin."
            : "Names and terms your calls say, so the transcript spells them right."}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-border/60 bg-background px-2.5 py-2">
        {items.map((item) => (
          <span
            key={item.id}
            title={item.phonetic_hints.length ? `Fixes: ${item.phonetic_hints.join(", ")}` : undefined}
            className="inline-flex items-center gap-1 rounded-full bg-secondary/10 py-1 pl-2.5 pr-2 text-xs text-foreground"
          >
            {item.target_word}
            {!readOnly && (
              <button
                type="button"
                aria-label={`Remove ${item.target_word}`}
                disabled={removingId === item.id}
                onClick={() => void remove(item)}
                className="text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                <X className="h-3 w-3" strokeWidth={1.5} />
              </button>
            )}
          </span>
        ))}
        {!readOnly && (
          <input
            value={draft}
            disabled={adding}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                void add();
              }
            }}
            onBlur={() => draft.trim() && void add()}
            placeholder={items.length ? "Add a word…" : "Add names, products, jargon…"}
            aria-label="Add a word to the glossary"
            className="min-w-[8rem] flex-1 bg-transparent px-1 py-1 text-xs outline-none placeholder:text-muted-foreground/60"
          />
        )}
        {readOnly && items.length === 0 && <span className="px-1 py-1 text-xs text-muted-foreground">No terms yet.</span>}
      </div>
    </div>
  );
};
