import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/features/auth";
import { HosFilters, HosPageHeader } from "@/features/head-of-sales/HosFilters";
import { HosPeopleTable } from "@/features/head-of-sales/HosOverview";
import { HosSummary } from "@/features/head-of-sales/HosSummary";
import { ProcessHealth } from "@/features/head-of-sales/ProcessHealth";
import { useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { HOS_DEFAULT_PERIOD, PROCESS_HREF, type HosPeriod, type HosSalesRole } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { usesRepHome } from "@/lib/nav";
import { showProcessAnalytics } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { parseTab } from "@/lib/url-tab";

const TABS = ["summary", "people", "working"] as const;

/**
 * Head of Sales Equipo, one question per tab: Resumen (how the team is doing), Personas (each
 * person) and Cómo está funcionando (is it the rep or the playbook, and which objections come up).
 */
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
          <Button asChild variant="quiet" size="text" className="shrink-0">
            <Link to="/dashboard/today">{p.hosGoToToday}</Link>
          </Button>
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
            <TabsTrigger value="working" className={THEME_TOKENS.interaction.segmentTab}>
              {p.pb2.analyticsTitle}
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
        <TabsContent value="working" className="mt-0">
          <Working period={period} salesRole={salesRole} />
        </TabsContent>
      </Tabs>
    </main>
  );
}

/** One row per person, the rep page one click away. */
function People({ period, salesRole, showRepDetail }: { period: HosPeriod; salesRole: HosSalesRole; showRepDetail: boolean }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useTeamAdherence(period, salesRole, { withFocus: true });

  if (query.isError) return <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>;
  if (query.isLoading) return <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p>;
  return (
    <HosPeopleTable
      reps={query.data?.reps ?? []}
      showRepDetail={showRepDetail}
      csvName={`team-${period}.csv`}
      period={period}
      stale={query.isPlaceholderData}
    />
  );
}

/** Whether the process works (rep problem or playbook problem) and the objections behind it, once there are scored calls. */
function Working({ period, salesRole }: { period: HosPeriod; salesRole: HosSalesRole }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useTeamAdherence(period, salesRole);
  const filtered = period !== HOS_DEFAULT_PERIOD || salesRole !== "all";

  if (query.isError) return <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>;
  if (query.isLoading) return <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p>;
  if (!query.data || !showProcessAnalytics(query.data, filtered)) {
    return (
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} flex flex-wrap items-center justify-between gap-4 p-5`}>
        <p className={`${THEME_TOKENS.typography.body} max-w-xl`}>{p.hosDiagNoProcess}</p>
        <Button asChild variant="outline" size="sm">
          <Link to={PROCESS_HREF}>{p.hosProcessDefineHeading}</Link>
        </Button>
      </div>
    );
  }
  return (
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
  );
}
