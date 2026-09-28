import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLanguage } from "@/lib/i18n";
import {
  trendBarRatio,
  trendCellText,
  trendHasConversations,
  trendRows,
  trendSampleLimited,
  trendWeekLabel,
  type TrendPayload,
  type TrendWeek,
} from "@/lib/team-adherence-trend";
import type { TeamFilters } from "@/lib/team-insights";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { ApiError, api } from "@/shared/lib/api-client";

function trendPath(filters: TeamFilters): string {
  const params = new URLSearchParams();
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.motion) params.set("motion", filters.motion);
  const qs = params.toString();
  return qs ? `/team/adherence/trend?${qs}` : "/team/adherence/trend";
}

function Bar({ week, title }: { week: TrendWeek; title: string }) {
  const ratio = trendBarRatio(week);
  const changed = week.new_playbook_version ? "border-l border-foreground/50 pl-px" : "";
  return (
    <span title={title} className={`flex h-6 w-3 items-end ${changed}`}>
      {week.state === "gap" ? (
        <span className="h-full w-full rounded-sm border border-dashed border-border" />
      ) : ratio === null ? (
        <span className="h-1 w-full rounded-sm bg-muted-foreground/40" />
      ) : (
        <span className="relative h-full w-full overflow-hidden rounded-sm bg-secondary">
          <span className="absolute inset-x-0 bottom-0 bg-primary" style={{ height: `${Math.max(ratio, 0.04) * 100}%` }} />
        </span>
      )}
    </span>
  );
}

export function AdherenceTrend({ filters }: { filters: TeamFilters }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useQuery({
    queryKey: ["team-adherence-trend", filters],
    queryFn: () => api.get<TrendPayload>(trendPath(filters)),
    retry: false,
  });
  // 404 is the flag being off for this company: nothing new appears. Reserving space while
  // loading would make every flag-off card jump, so loading renders nothing too.
  const hidden = query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 403);
  if (hidden || query.isLoading) return null;
  if (query.isError || query.data?.coverage !== "complete") {
    return <p className={`border-t border-border/70 pt-4 ${THEME_TOKENS.typography.body}`}>{p.teamTrendFailed}</p>;
  }
  const payload = query.data;
  const rows = trendRows(payload, p.teamTitle);
  const heading = p.teamTrendHeading.replace("{weeks}", String(payload.weeks.length));
  const labels = payload.weeks.map((week) => trendWeekLabel(week.week_start, p.hourLocale));
  return (
    <div className="space-y-3 border-t border-border/70 pt-4">
      <h3 className={THEME_TOKENS.typography.capsLabel}>{heading}</h3>
      {!trendHasConversations(rows) ? (
        <p className={THEME_TOKENS.typography.body}>{p.teamTrendEmpty}</p>
      ) : (
        <>
          <ul className="space-y-2" aria-hidden="true">
            {rows.map((row) => (
              <li key={row.key} className="flex items-center gap-3 text-sm">
                <span className="w-32 truncate text-foreground">{row.name}</span>
                <span className="flex gap-1">
                  {row.weeks.map((week, index) => (
                    <Bar key={week.week_start} week={week} title={`${labels[index]}: ${trendCellText(week, p)}`} />
                  ))}
                </span>
              </li>
            ))}
          </ul>
          <p className={THEME_TOKENS.typography.capsLabel}>{p.teamTrendLegend}</p>
          {trendSampleLimited(rows) ? <p className={THEME_TOKENS.typography.capsLabel}>{p.sampleLimited}</p> : null}
          <details>
            <summary className="cursor-pointer text-sm text-muted-foreground">{p.teamTrendDetail}</summary>
            <Table className="mt-2 text-sm">
              <TableHeader>
                <TableRow>
                  <TableHead>{p.teamTrendWeek}</TableHead>
                  {rows.map((row) => (
                    <TableHead key={row.key}>{row.name}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {payload.weeks.map((week, index) => (
                  <TableRow key={week.week_start}>
                    <TableCell className="whitespace-nowrap">{labels[index]}</TableCell>
                    {rows.map((row) => (
                      <TableCell key={row.key}>{trendCellText(row.weeks[index], p)}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </details>
        </>
      )}
    </div>
  );
}
