import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipProps } from "recharts";
import type { TrendWeek } from "@/features/team/types";
import { formatCount, formatWeek } from "./format";

function TrendTooltip({ active, payload }: TooltipProps<number, string>) {
  const week = payload?.[0]?.payload as TrendWeek | undefined;
  if (!active || !week) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-sm">
      <p className="text-foreground mb-1">Week of {formatWeek(week.weekStart)}</p>
      <p className="text-muted-foreground">
        <span className="text-foreground tabular-nums">{formatCount(week.calls)}</span> calls
      </p>
      <p className="text-muted-foreground">
        <span className="text-foreground tabular-nums">{formatCount(week.connected)}</span> connected
      </p>
      <p className="text-muted-foreground">
        <span className="text-foreground tabular-nums">{formatCount(week.useful)}</span> useful conversations
      </p>
    </div>
  );
}

/** Calls per week. One series, so no legend: the card title names it. */
export function WeeklyTrendChart({ weeks }: { weeks: TrendWeek[] }) {
  return (
    <div className="h-52" role="img" aria-label="Calls per week">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={weeks} margin={{ top: 8, right: 8, bottom: 0, left: -16 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeOpacity={0.6} />
          <XAxis
            dataKey="weekStart"
            tickFormatter={formatWeek}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          />
          <YAxis
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          />
          <Tooltip cursor={{ fill: "hsl(var(--secondary))", fillOpacity: 0.5 }} content={<TrendTooltip />} />
          <Bar dataKey="calls" fill="hsl(var(--chart-activity))" radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
