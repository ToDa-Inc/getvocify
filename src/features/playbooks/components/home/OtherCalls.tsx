import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { HomeType } from "@/features/playbooks/components/home/FunnelBlock";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * "¿Quieres que Vocify te ayude en otro tipo de llamadas?": calls outside the sales funnel (support, a technical call). They are
 * not scored in coaching; they can have steps, or only the information Vocify should give when asked.
 */
export function OtherCalls({ types, canEdit, onCreate, onOpen }: { types: HomeType[]; canEdit: boolean; onCreate: () => void; onOpen: (key: string) => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  if (!types.length && !canEdit) return null;
  return (
    <section aria-labelledby="home-other" className="mx-auto flex max-w-2xl flex-col items-center gap-6 border-t border-border/50 pt-10 text-center">
      <header className="space-y-2">
        <h2 id="home-other" className={THEME_TOKENS.typography.sectionTitle}>
          {c.otherTitle}
        </h2>
        <p className="text-[14px] leading-relaxed text-muted-foreground">{c.otherLead}</p>
      </header>
      {types.length ? (
        <ul className="flex w-full flex-col items-center gap-3">
          {types.map((type) => (
            <li key={type.key} className="flex w-full flex-wrap items-center justify-center gap-x-4 gap-y-1">
              <button
                type="button"
                onClick={() => onOpen(type.key)}
                className={cn(
                  "min-w-[10rem] rounded-full border border-border/80 px-6 py-2.5 text-[15px] font-medium text-foreground transition-colors duration-150 hover:border-beige/50 hover:bg-secondary/40",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                {type.label}
              </button>
              {type.description ? <span className="text-[13px] text-muted-foreground">{type.description}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {canEdit ? (
        <Button type="button" variant="outline" onClick={onCreate}>
          <Plus aria-hidden strokeWidth={1.5} />
          {c.createOther}
        </Button>
      ) : null}
    </section>
  );
}
