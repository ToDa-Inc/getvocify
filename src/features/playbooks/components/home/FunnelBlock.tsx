import type { ReactNode } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { afterColon, nextStep } from "@/lib/playbook-home";
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

/** One step of the process: its number on a line that joins it to the next, its name, and what it takes to move on. */
function StepRow({ number, last, children }: { number: number; last: boolean; children: ReactNode }) {
  return (
    <li className="grid grid-cols-[1.75rem_1fr] gap-x-3">
      <span className="flex flex-col items-center" aria-hidden>
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs tabular-nums text-muted-foreground">{number}</span>
        {last ? null : <span className="w-px flex-1 bg-border" />}
      </span>
      <div className={cn("min-w-0", last ? "pb-1" : "pb-5")}>{children}</div>
    </li>
  );
}

/** The empty process as a sketch: three dotted steps in order, and a "Crear +" that opens the window to define it. */
function EmptyProcess({ onCreate, canEdit }: { onCreate: () => void; canEdit: boolean }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const sketch = ["Cold call", "Discovery", "···"];
  const body = (
    <>
      <ol className="w-full max-w-[16rem] text-left" aria-hidden>
        {sketch.map((label, index) => (
          <StepRow key={label} number={index + 1} last={index === sketch.length - 1}>
            <span className="block pt-1 text-[15px] text-muted-foreground/60">{label}</span>
          </StepRow>
        ))}
      </ol>
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
 * "Proceso de venta": the interactions the company runs to close a customer, as numbered steps in order. Under each name,
 * what it takes to move to the next step (the last one: to close); a click opens everything about it.
 */
export function FunnelBlock({ types, canEdit, onCreate, onEdit, onOpen }: { types: HomeType[]; canEdit: boolean; onCreate: () => void; onEdit: () => void; onOpen: (key: string) => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
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
          <ol className="w-full max-w-md">
            {types.map((type, index) => {
              const next = nextStep(types, index);
              return (
                <StepRow key={type.key} number={index + 1} last={next === null}>
                  <button
                    type="button"
                    onClick={() => onOpen(type.key)}
                    className={cn(
                      "-mx-2 -mt-0.5 block w-[calc(100%+1rem)] rounded-md px-2 py-1 text-left",
                      THEME_TOKENS.interaction.rowHover,
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      THEME_TOKENS.motion.fadeIn,
                    )}
                  >
                    <span className="flex items-center gap-2.5">
                      <span className={cn("min-w-0 truncate", THEME_TOKENS.typography.itemTitle)}>{type.label}</span>
                      <span aria-hidden className={cn("h-2 w-2 shrink-0 rounded-full", DOT[type.state])} />
                    </span>
                    <span className="mt-0.5 block text-[13px] leading-snug text-muted-foreground">
                      {type.goal ? (
                        <>
                          <span className="text-muted-foreground/70">{next === null ? c.stepToClose : c.stepToNext.replace("{next}", next || c.nextFallback)}</span>{" "}
                          {afterColon(type.goal)}
                        </>
                      ) : (
                        <span className="text-warning">{c.stepNoGoal}</span>
                      )}
                    </span>
                  </button>
                </StepRow>
              );
            })}
          </ol>
          {canEdit ? (
            <Button type="button" variant="quiet" size="text" onClick={onEdit}>
              {c.edit}
            </Button>
          ) : null}
        </>
      ) : (
        <div className="w-full max-w-md">
          <EmptyProcess onCreate={onCreate} canEdit={canEdit} />
        </div>
      )}
    </section>
  );
}
