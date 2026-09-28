import { useState } from "react";
import { useAuth } from "@/features/auth";
import { HosFilters, HosPageHeader } from "@/features/head-of-sales/HosFilters";
import { HosPeopleTable } from "@/features/head-of-sales/HosOverview";
import { useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import { HOS_DEFAULT_PERIOD, type HosPeriod, type HosSalesRole } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Head of Sales Equipo (plan §3.2): one row per person, the rep page one click away. */
export default function HeadOfSalesTeamPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const [period, setPeriod] = useState<HosPeriod>(HOS_DEFAULT_PERIOD);
  const [salesRole, setSalesRole] = useState<HosSalesRole>("all");
  const query = useTeamAdherence(period, salesRole, { withFocus: true });
  const features = user?.company?.features ?? [];

  return (
    <main className={`max-w-5xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <HosPageHeader title={p.teamTitle} subtitle={p.hosTeamSubtitle} />
      <HosFilters
        period={period}
        salesRole={salesRole}
        onPeriod={setPeriod}
        onSalesRole={setSalesRole}
        showRoles={features.includes("SALES_ROLES_ENABLED")}
      />
      {query.isError ? (
        <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>
      ) : query.isLoading ? (
        <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p>
      ) : (
        <HosPeopleTable
          reps={query.data?.reps ?? []}
          showRepDetail={features.includes("MANAGER_HOME_ENABLED")}
          csvName={`team-${period}.csv`}
          period={period}
          stale={query.isPlaceholderData}
        />
      )}
    </main>
  );
}
