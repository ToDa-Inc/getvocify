import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useAuth } from "@/features/auth";
import { teamApi, teamKeys } from "@/features/team/api";
import type { PeriodPreset, SalesRoleFilter, TeamMetrics } from "@/features/team/types";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { IconAction } from "@/components/ui/icon-action";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { KpiTile } from "@/components/dashboard/sales/KpiTile";
import { ActivityFunnel } from "@/components/dashboard/sales/ActivityFunnel";
import { WeeklyTrendChart } from "@/components/dashboard/sales/WeeklyTrendChart";
import { TeamActivityTable } from "@/components/dashboard/sales/TeamActivityTable";
import {
  PERIOD_OPTIONS,
  countDelta,
  formatCount,
  formatDayRange,
  formatPercent,
  rateDelta,
} from "@/components/dashboard/sales/format";

type Tab = "overview" | "team";

const TABS: { value: Tab; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "team", label: "Team" },
];

const ROLE_FILTERS: { value: SalesRoleFilter; label: string }[] = [
  { value: "all", label: "Everyone" },
  { value: "sdr", label: "SDRs" },
  { value: "ae", label: "AEs" },
];

const pill = (active: boolean) =>
  `${THEME_TOKENS.interaction.navPill} ${
    active ? THEME_TOKENS.interaction.navPillActive : THEME_TOKENS.interaction.navPillIdle
  }`;

function Card({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 md:p-6`}>
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{title}</h2>
      <p className="text-xs text-muted-foreground mt-1 mb-5 leading-relaxed">{subtitle}</p>
      {children}
    </section>
  );
}

function EmptyRole({ role }: { role: SalesRoleFilter }) {
  const who = role === "sdr" ? "SDRs" : role === "ae" ? "AEs" : "active members";
  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center`}>
      <p className="text-sm text-foreground">No {who} in this workspace yet.</p>
      <p className="text-xs text-muted-foreground mt-1.5">
        Set each person's position in{" "}
        <Link to="/dashboard/settings/team" className="underline underline-offset-2 hover:text-foreground">
          Settings → Team
        </Link>{" "}
        so the dashboard can compare SDRs with SDRs and AEs with AEs.
      </p>
    </div>
  );
}

function Overview({ data, comparison, periodLabel }: { data: TeamMetrics; comparison: string; periodLabel: string }) {
  const now = data.team.current;
  const before = data.team.previous;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <KpiTile
          testId="kpi-calls"
          label="Calls"
          value={formatCount(now.calls)}
          delta={countDelta(now.calls, before.calls)}
          comparison={comparison}
          hint="Calls placed from the Vocify dialer."
        />
        <KpiTile
          testId="kpi-connection"
          label="Connection rate"
          value={formatPercent(now.connectionRate)}
          delta={rateDelta(now.connectionRate, before.connectionRate)}
          comparison={comparison}
          hint="Connected calls ÷ calls. Low with normal volume points to lists or timing, not technique."
        />
        <KpiTile
          testId="kpi-useful"
          label="Useful conversations"
          value={formatCount(now.useful)}
          delta={countDelta(now.useful, before.useful)}
          comparison={comparison}
          hint={`Connected calls lasting at least ${data.usefulCallSeconds} seconds.`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Where calls drop off" subtitle={`${periodLabel} · each step as a share of the one before`}>
          <ActivityFunnel
            steps={[
              { label: "Calls", value: now.calls },
              { label: "Connected", value: now.connected },
              { label: "Useful conversations", value: now.useful },
            ]}
          />
        </Card>
        <Card title="Calls per week" subtitle={`${periodLabel} · hover a week for connected and useful calls`}>
          <WeeklyTrendChart weeks={data.trend} />
        </Card>
      </div>

      {data.unavailable.length > 0 && (
        <p className="text-xs text-muted-foreground leading-relaxed" data-testid="coming-next">
          Coming next on this page: {data.unavailable.map((u) => u.reason).join(" ")}
        </p>
      )}
    </div>
  );
}

const SalesTeamPage = () => {
  const { user } = useAuth();
  const canView = user?.company?.role === "owner" || user?.company?.role === "admin";
  const [tab, setTab] = useState<Tab>("overview");
  const [period, setPeriod] = useState<PeriodPreset>("month");
  const [salesRole, setSalesRole] = useState<SalesRoleFilter>("all");

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: teamKeys.metrics(period, salesRole),
    queryFn: () => teamApi.getMetrics(period, salesRole),
    enabled: canView,
    placeholderData: (previous) => previous,
  });

  if (!canView) {
    return (
      <div className="max-w-5xl mx-auto">
        <p className={THEME_TOKENS.typography.body}>Only owners and admins can see team performance.</p>
      </div>
    );
  }

  const periodOption = PERIOD_OPTIONS.find((o) => o.value === period) ?? PERIOD_OPTIONS[1];
  const periodLabel = data ? formatDayRange(data.period.start, data.period.end) : periodOption.label;
  const updatedAt = data
    ? new Date(data.generatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className={`max-w-5xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={`${V_PATTERNS.dashboardHeader} flex items-start justify-between gap-4`}>
        <div className="space-y-1.5">
          <h1 className={THEME_TOKENS.typography.pageTitle}>Sales team</h1>
          <p className={THEME_TOKENS.typography.body}>How your team is doing, and where it gets stuck.</p>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground shrink-0 pt-2">
          {updatedAt && <span data-testid="updated-at">Updated {updatedAt}</span>}
          <IconAction
            label="Refresh"
            pendingLabel="Refreshing…"
            pending={isFetching}
            onClick={() => void refetch()}
          >
            <RefreshCw className="h-4 w-4" />
          </IconAction>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <nav aria-label="Sales team sections" className="flex gap-1">
          {TABS.map((t) => (
            <button key={t.value} type="button" className={pill(tab === t.value)} aria-pressed={tab === t.value} onClick={() => setTab(t.value)}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <div className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1" role="group" aria-label="Position">
            {ROLE_FILTERS.map((r) => (
              <button
                key={r.value}
                type="button"
                aria-pressed={salesRole === r.value}
                onClick={() => setSalesRole(r.value)}
                className={`rounded-full px-3.5 h-7 text-xs transition-colors ${
                  salesRole === r.value ? "bg-beige text-cream" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <Select value={period} onValueChange={(v) => setPeriod(v as PeriodPreset)}>
            <SelectTrigger className="h-9 w-[12.5rem] rounded-full text-xs" aria-label="Period">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {isLoading && (
        <div className={THEME_TOKENS.interaction.pageLoad}>
          <VocifyLoader size="lg" label="Loading team activity..." />
        </div>
      )}

      {isError && !data && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center`}>
          <p className="text-sm text-foreground">Could not load team activity.</p>
          <button type="button" className="text-xs text-muted-foreground underline mt-2" onClick={() => void refetch()}>
            Try again
          </button>
        </div>
      )}

      {data && data.members.length === 0 && <EmptyRole role={salesRole} />}

      {data && data.members.length > 0 && tab === "overview" && (
        <Overview data={data} comparison={periodOption.comparison} periodLabel={periodLabel} />
      )}

      {data && data.members.length > 0 && tab === "team" && (
        <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} pt-5 overflow-hidden`}>
          <div className="px-5 md:px-6">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>Activity by person</h2>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              {periodLabel} · sorted by calls · change in calls vs {periodOption.comparison}
            </p>
          </div>
          <TeamActivityTable
            members={data.members}
            total={data.team.current}
            median={data.team.median}
            usefulCallSeconds={data.usefulCallSeconds}
            periodLabel={periodLabel}
          />
        </section>
      )}
    </div>
  );
};

export default SalesTeamPage;
