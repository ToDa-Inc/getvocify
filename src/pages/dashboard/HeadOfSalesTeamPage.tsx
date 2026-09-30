import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/features/auth";
import { HosFilters, HosPageHeader } from "@/features/head-of-sales/HosFilters";
import { HosPeopleTable } from "@/features/head-of-sales/HosOverview";
import { HosSummary } from "@/features/head-of-sales/HosSummary";
import { ProcessHealth } from "@/features/head-of-sales/ProcessHealth";
import { useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { HOS_DEFAULT_PERIOD, type HosPeriod, type HosSalesRole } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { usesRepHome } from "@/lib/nav";
import { showProcessAnalytics } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { parseTab } from "@/lib/url-tab";

const TABS = ["summary", "people"] as const;

/** Head of Sales Equipo: Resumen (how the team is doing) and Personas (each person, and whether the process works). */
export default function HeadOfSalesTeamPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab"), TABS, "summary");
  // One period and position for both tabs: switching tab keeps what the Head of Sales is looking at.
  const [period, setPeriod] = useState<HosPeriod>(HOS_DEFAULT_PERIOD);
  const [salesRole, setSalesRole] = useState<HosSalesRole>("all");
  const features = user?.company?.features ?? [];

  const selectTab = (next: string) =>
    setParams(
      (previous) => {
        const search = new URLSearchParams(previous);
        search.set("tab", next);
        return search;
      },
      { replace: true },
    );

  return (
    <main className={`max-w-5xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="flex items-start justify-between gap-4">
        <HosPageHeader title={p.teamTitle} subtitle={p.hosSummarySubtitle} />
        {/* T13: a Head of Sales who also sells keeps a way to their own day, off the menu. */}
        {usesRepHome(user?.company) ? (
          <Link className="shrink-0 pt-2 text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground" to="/dashboard/today">
            {p.hosGoToToday}
          </Link>
        ) : null}
      </div>
      <Tabs value={tab} onValueChange={selectTab} className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList aria-label={p.teamTitle} className={THEME_TOKENS.interaction.segmentList}>
            <TabsTrigger value="summary" className={THEME_TOKENS.interaction.segmentTab}>
              {p.hosSummaryTitle}
            </TabsTrigger>
            <TabsTrigger value="people" className={THEME_TOKENS.interaction.segmentTab}>
              {p.hosPeopleTab}
            </TabsTrigger>
          </TabsList>
          <HosFilters
            period={period}
            salesRole={salesRole}
            onPeriod={setPeriod}
            onSalesRole={setSalesRole}
            showRoles={features.includes("SALES_ROLES_ENABLED")}
          />
        </div>
        <TabsContent value="summary" className="mt-0">
          <HosSummary period={period} salesRole={salesRole} />
        </TabsContent>
        <TabsContent value="people" className="mt-0">
          <People period={period} salesRole={salesRole} showRepDetail={features.includes("MANAGER_HOME_ENABLED")} />
        </TabsContent>
      </Tabs>
    </main>
  );
}

/** One row per person, the rep page one click away; then whether the process works, once there are scored calls. */
function People({ period, salesRole, showRepDetail }: { period: HosPeriod; salesRole: HosSalesRole; showRepDetail: boolean }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useTeamAdherence(period, salesRole, { withFocus: true });
  const filtered = period !== HOS_DEFAULT_PERIOD || salesRole !== "all";

  if (query.isError) return <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>;
  if (query.isLoading) return <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p>;
  return (
    <div className="space-y-6">
      <HosPeopleTable
        reps={query.data?.reps ?? []}
        showRepDetail={showRepDetail}
        csvName={`team-${period}.csv`}
        period={period}
        stale={query.isPlaceholderData}
      />
      {query.data && showProcessAnalytics(query.data, filtered) ? (
        <div
          className={`space-y-6 transition-opacity ${query.isPlaceholderData ? "opacity-50" : ""}`}
          aria-busy={query.isPlaceholderData}
        >
          <ProcessHealth flows={query.data.process_health ?? []} />
          <ObjectionBreakdown
            categories={query.data.objection_categories ?? []}
            competitors={query.data.competitor_mentions}
            sampleLimited={query.data.sample_limited === true}
            emptyText={period === "week" ? undefined : p.hosObjectionsEmptyPeriod}
          />
        </div>
      ) : null}
    </div>
  );
}
