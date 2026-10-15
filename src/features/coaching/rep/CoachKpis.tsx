import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, CalendarCheck, Gauge, MessagesSquare, ShieldCheck } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { fill, formatPercent, summarizeCalls, trendOf, type CoachCalls } from "@/lib/rep-coaching";
import { cn } from "@/lib/utils";

function Tile({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: string; sub?: ReactNode; tone?: string }) {
  return (
    <div className="min-w-0 space-y-1 px-3 py-3 md:px-4 md:first:pl-3">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        <span>{label}</span>
      </p>
      <p className={cn("text-[22px] font-medium md:text-[26px] leading-none tracking-tight tabular-nums text-foreground", tone)}>{value}</p>
      <p className="min-h-4 text-xs text-muted-foreground">{sub}</p>
    </div>
  );
}

/** The window at a glance, four numbers from what the page already has: how many conversations, how much
 * of the process got done (and whether that is going up), how many objections were resolved, how many
 * meetings were agreed. A row, not cards: it frames the tables under it, it does not compete with them. */
export function CoachKpis({ data }: { data: CoachCalls }) {
  const { t } = useLanguage();
  const p = t.product;
  const channels = p.pb2.ruleChannels as Record<string, string>;
  const summary = summarizeCalls(data.calls);
  const objections = (data.objections ?? []).reduce((sum, item) => ({ total: sum.total + item.total, resolved: sum.resolved + item.resolved }), { total: 0, resolved: 0 });
  const trend = summary.recent ? trendOf(summary.recent.rate, summary.recent.prev) : null;
  const points = summary.recent ? Math.round((summary.recent.rate - summary.recent.prev) * 100) : 0;
  const kinds = Object.entries(summary.byKind);
  const split = kinds.length > 1 ? kinds.map(([kind, count]) => `${count} ${(channels[kind] ?? kind).toLowerCase()}`).join(" · ") : fill(p.coachKpiWindow, { weeks: data.window_weeks });
  const TrendIcon = trend === "up" ? ArrowUp : ArrowDown;

  return (
    <div className="grid grid-cols-2 divide-border/50 border-y border-border/50 md:grid-cols-4 md:divide-x" data-testid="coach-kpis">
      <Tile icon={<MessagesSquare aria-hidden size={13} strokeWidth={1.5} />} label={p.coachKpiConversations} value={String(summary.conversations)} sub={split} />
      <Tile
        icon={<Gauge aria-hidden size={13} strokeWidth={1.5} />}
        label={p.coachKpiProcess}
        value={formatPercent(summary.rate)}
        sub={
          trend && trend !== "flat" ? (
            <span className={cn("inline-flex items-center gap-1", trend === "up" ? "text-success" : "text-destructive")}>
              <TrendIcon aria-hidden className="h-3 w-3" strokeWidth={2} />
              {Math.abs(points)} pts <span className="text-muted-foreground">{p.coachKpiVsBefore}</span>
            </span>
          ) : (
            fill(p.coachKpiWindow, { weeks: data.window_weeks })
          )
        }
      />
      {objections.total ? (
        <Tile
          icon={<ShieldCheck aria-hidden size={13} strokeWidth={1.5} />}
          label={p.coachKpiObjections}
          value={`${objections.resolved}/${objections.total}`}
          sub={formatPercent(objections.resolved / objections.total)}
        />
      ) : null}
      {summary.meetings ? (
        <Tile
          icon={<CalendarCheck aria-hidden size={13} strokeWidth={1.5} />}
          label={p.coachKpiMeetings}
          value={String(summary.meetings)}
          sub={fill(p.coachKpiOf, { total: summary.conversations })}
        />
      ) : null}
    </div>
  );
}
