import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { funnelWidths } from "@/lib/playbook-home";
import type { PublishState } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export type HomeType = { key: string; label: string; goal: string | null; description: string | null; stage: string; state: PublishState };

const DOT: Record<PublishState, string> = {
  live: "bg-success",
  changes: "bg-warning",
  unpublished: "bg-beige",
  paused: "bg-muted-foreground/40",
  empty: "border border-muted-foreground/50",
};

/** The empty funnel as a sketch: three dotted steps, wide to narrow, and a "Crear +" that opens the window to define it. */
function EmptyFunnel({ onCreate, canEdit }: { onCreate: () => void; canEdit: boolean }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const widths = funnelWidths(3);
  const sketch = ["Cold call", "Discovery", "···"];
  const body = (
    <>
      <span className="flex w-full flex-col items-center gap-3" aria-hidden>
        {sketch.map((label, index) => (
          <span
            key={label}
            style={{ width: `${widths[index] * 100}%` }}
            className="rounded-full border border-dashed border-border py-3 text-center text-sm text-muted-foreground/60"
          >
            {label}
          </span>
        ))}
      </span>
      {canEdit ? (
        <span className="inline-flex items-center gap-2 pt-2 text-[17px] font-medium text-muted-foreground transition-colors group-hover:text-foreground">
          {c.create}
          <Plus aria-hidden className="h-5 w-5" strokeWidth={1.75} />
        </span>
      ) : null}
    </>
  );
  const frame = cn("flex min-h-[19rem] w-full flex-col items-center justify-center gap-5 border border-dashed border-border px-8 py-8", THEME_TOKENS.radius.container);
  return canEdit ? (
    <button
      type="button"
      onClick={onCreate}
      className={cn("group", frame, "transition-colors duration-150 hover:border-beige/40 hover:bg-secondary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
    >
      {body}
    </button>
  ) : (
    <div className={frame}>{body}</div>
  );
}

/**
 * "Funnel de ventas": the interactions the company runs to close a customer, drawn as a funnel (the first is the widest, the
 * last the narrowest). A step shows its name and, under it, what it must achieve; a click opens everything about it.
 */
export function FunnelBlock({ types, canEdit, onCreate, onEdit, onOpen }: { types: HomeType[]; canEdit: boolean; onCreate: () => void; onEdit: () => void; onOpen: (key: string) => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const widths = funnelWidths(types.length);
  return (
    <section aria-labelledby="home-funnel" className="flex min-w-0 flex-col items-center gap-8">
      <header className="max-w-md space-y-2 text-center lg:min-h-[7rem]">
        <h2 id="home-funnel" className={THEME_TOKENS.typography.panelTitle}>
          {c.funnelTitle}
        </h2>
        <p className="text-[15px] leading-relaxed text-muted-foreground">{types.length ? c.funnelLead : c.funnelEmptyLead}</p>
      </header>
      {types.length ? (
        <>
          <ol className="flex w-full max-w-md flex-col items-center gap-1">
            {types.map((type, index) => (
              <li key={type.key} className="flex w-full flex-col items-center gap-1.5 pb-2" style={{ animationDelay: `${index * 40}ms` }}>
                <button
                  type="button"
                  onClick={() => onOpen(type.key)}
                  style={{ width: `${widths[index] * 100}%` }}
                  className={cn(
                    "flex items-center justify-center gap-2.5 rounded-full border border-border/80 px-5 py-3.5 text-[16px] font-medium text-foreground",
                    "transition-colors duration-150 motion-reduce:transition-none hover:border-beige/50 hover:bg-secondary/40",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    THEME_TOKENS.motion.fadeIn,
                  )}
                >
                  <span aria-hidden className={cn("h-2 w-2 shrink-0 rounded-full", DOT[type.state])} />
                  <span className="min-w-0 truncate">{type.label}</span>
                </button>
                {type.goal ? <p className="max-w-[16rem] text-center text-[13px] leading-snug text-muted-foreground">{type.goal}</p> : null}
              </li>
            ))}
          </ol>
          {canEdit ? (
            <Button type="button" variant="quiet" size="text" onClick={onEdit}>
              {c.edit}
            </Button>
          ) : null}
        </>
      ) : (
        <div className="w-full max-w-md">
          <EmptyFunnel onCreate={onCreate} canEdit={canEdit} />
        </div>
      )}
    </section>
  );
}
