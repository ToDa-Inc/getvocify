import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { COMPANY_AREAS, type CompanyAreaId, type CompanyOpens } from "@/lib/playbook-home";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export type CompanyAreaState = { id: CompanyAreaId; filled: boolean };

/**
 * "Vuestra empresa": what Vocify knows about the company, its product and its offer. Empty, it is a sketch with a "Crear +" that
 * opens the window to fill it; filled, the six areas are listed with whether each has something, and a click opens that one.
 */
export function CompanyBlock({ areas, canEdit, onCreate, onOpen }: { areas: CompanyAreaState[]; canEdit: boolean; onCreate: () => void; onOpen: (opens: CompanyOpens) => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const labels = c as unknown as Record<string, string>;
  const any = areas.some((area) => area.filled);
  const frame = cn("flex min-h-[19rem] w-full flex-col items-center justify-center gap-6 border border-dashed border-border px-8 py-8", THEME_TOKENS.radius.container);
  const sketch = (
    <>
      <span aria-hidden className="grid w-full grid-cols-3 gap-x-4 gap-y-6 py-4 text-center text-[15px] text-muted-foreground/60">
        {COMPANY_AREAS.map((area) => (
          <span key={area.id}>{labels[`area_${area.id}`]}</span>
        ))}
      </span>
      {canEdit ? (
        <span className="inline-flex items-center gap-2 text-[17px] font-medium text-muted-foreground transition-colors group-hover:text-foreground">
          {c.create}
          <Plus aria-hidden className="h-5 w-5" strokeWidth={1.75} />
        </span>
      ) : null}
    </>
  );
  return (
    <section aria-labelledby="home-company" className="flex min-w-0 flex-col items-center gap-8">
      <header className="max-w-md space-y-2 text-center lg:min-h-[7rem]">
        <h2 id="home-company" className={THEME_TOKENS.typography.panelTitle}>
          {c.companyTitle}
        </h2>
        <p className="text-[15px] leading-relaxed text-muted-foreground">{any ? c.companyLead : c.companyEmptyLead}</p>
      </header>
      {any ? (
        <>
          <ul className="w-full max-w-md divide-y divide-border/50 border-y border-border/50">
            {areas.map((area) => {
              const opens = COMPANY_AREAS.find((item) => item.id === area.id)?.opens ?? "notes";
              return (
                <li key={area.id}>
                  <button
                    type="button"
                    onClick={() => onOpen(opens)}
                    className={cn("flex w-full items-center gap-3 px-2 py-3.5 text-left text-[16px] text-foreground", THEME_TOKENS.interaction.rowHover, "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
                  >
                    <span aria-hidden className={cn("h-2 w-2 shrink-0 rounded-full", area.filled ? "bg-success" : "border border-muted-foreground/50")} />
                    <span className="flex-1">{labels[`area_${area.id}`]}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {canEdit ? (
            <Button type="button" variant="quiet" size="text" onClick={() => onOpen("notes")}>
              {c.edit}
            </Button>
          ) : null}
        </>
      ) : (
        <div className="w-full max-w-md">
          {canEdit ? (
            <button
              type="button"
              onClick={onCreate}
              className={cn("group", frame, "transition-colors duration-150 hover:border-beige/40 hover:bg-secondary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
            >
              {sketch}
            </button>
          ) : (
            <div className={frame}>{sketch}</div>
          )}
        </div>
      )}
    </section>
  );
}
