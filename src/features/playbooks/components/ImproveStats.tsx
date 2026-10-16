import type { ReactNode } from "react";
import { MessagesSquare, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { Coverage, SuccessStats } from "@/features/playbooks/assistantApi";
import { useLanguage } from "@/lib/i18n";
import { statFigure } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;

function Tile({ icon, label, value, sub, note }: { icon: ReactNode; label: string; value: string; sub: string; note?: string }) {
  return (
    <div className="min-w-0 space-y-1 px-4 py-4 md:px-5">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="shrink-0">{icon}</span>
        <span className="min-w-0 break-words">{label}</span>
      </p>
      <p className="text-[26px] font-medium leading-none tracking-tight tabular-nums text-foreground">{value}</p>
      <p className="text-xs leading-snug text-muted-foreground">{sub}</p>
      {note ? <p className="text-xs leading-snug text-muted-foreground/80">{note}</p> : null}
    </div>
  );
}

export type ImproveStatsViewProps = {
  coverage: Coverage;
  /** Absent while the success rate is not switched on: only the coverage shows, with a calm note. */
  success?: SuccessStats;
  refreshing: boolean;
  /** What the last "Actualizar" did, already in the person's language. */
  note: string | null;
  disabled: boolean;
  onRefresh: () => void;
};

/**
 * Two sober figures in the style of Inicio: how much of what customers raised had an answer of the team's own
 * (coverage), and of the times a rep said what Vocify suggested, how many settled it (success rate). A percentage
 * only from three cases; below that the plain count. "Actualizar" judges the next batch of finished calls, apart from
 * the calls themselves.
 */
export function ImproveStatsView({ coverage, success, refreshing, note, disabled, onRefresh }: ImproveStatsViewProps) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const fill = (text: string, values: Record<string, number>) => text.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
  const coverageSub = coverage.detected
    ? fill(c.statCoverageSub, { answered: coverage.answered, detected: coverage.detected })
    : c.statNone;
  const successSub = success && success.clear ? fill(c.statSuccessSub, { resolved: success.resolved, clear: success.clear }) : c.statNone;
  return (
    <section className="space-y-3" aria-label={c.improveTitle}>
      <div className={cn(card, "grid divide-border/50", success ? "grid-cols-1 divide-y md:grid-cols-2 md:divide-x md:divide-y-0" : "grid-cols-1")}>
        <Tile
          icon={<MessagesSquare aria-hidden size={13} strokeWidth={1.5} />}
          label={c.statCoverage}
          value={statFigure(coverage.answered, coverage.detected, c.of)}
          sub={coverageSub}
          note={coverage.detected && coverage.rate === null ? c.statFew : c.statWindow}
        />
        {success ? (
          <Tile
            icon={<ShieldCheck aria-hidden size={13} strokeWidth={1.5} />}
            label={c.statSuccess}
            value={statFigure(success.resolved, success.clear, c.of)}
            sub={successSub}
            note={success.clear && success.rate === null ? c.statFew : c.statWindow}
          />
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <p className="max-w-md text-xs leading-snug text-muted-foreground">{success ? c.successHint : c.successOff}</p>
        {success ? (
          <div className="flex items-center gap-3">
            {refreshing ? (
              <span className="inline-flex items-center gap-2 text-xs text-muted-foreground" role="status">
                <VocifySpinner size={12} />
                {c.refreshing}
              </span>
            ) : note ? (
              <span className="text-xs text-muted-foreground" role="status">
                {note}
              </span>
            ) : null}
            <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={onRefresh}>
              {c.refresh}
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}

/** The placeholder of the two figures while they are read. */
export function ImproveStatsSkeleton() {
  const { t } = useLanguage();
  return (
    <div className={cn(card, "grid grid-cols-1 gap-3 p-4 md:grid-cols-2")} role="status" aria-busy="true">
      <Skeleton className="h-16 w-full motion-reduce:animate-none" />
      <Skeleton className="h-16 w-full motion-reduce:animate-none" />
      <span className="sr-only">{t.product.pb2.improve.assistantLoading}</span>
    </div>
  );
}
