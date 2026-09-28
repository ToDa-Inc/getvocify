import { useState } from "react";
import { useAuth } from "@/features/auth";
import { HosFilters, HosPageHeader } from "@/features/head-of-sales/HosFilters";
import { ProcessHealth } from "@/features/head-of-sales/ProcessHealth";
import { useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import PlaybooksSection from "@/features/playbooks/components/PlaybooksSection";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { HOS_DEFAULT_PERIOD, type HosPeriod, type HosSalesRole } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Proceso de venta (plan §4–5): is the process working, what the market says, and the process itself. */
export default function SalesProcessPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const [period, setPeriod] = useState<HosPeriod>(HOS_DEFAULT_PERIOD);
  const [salesRole, setSalesRole] = useState<HosSalesRole>("all");
  const query = useTeamAdherence(period, salesRole);

  return (
    <main className={`max-w-5xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <HosPageHeader title={p.hosProcessTitle} subtitle={p.hosProcessPageSubtitle} />
      <HosFilters
        period={period}
        salesRole={salesRole}
        onPeriod={setPeriod}
        onSalesRole={setSalesRole}
        showRoles={Boolean(user?.company?.features?.includes("SALES_ROLES_ENABLED"))}
      />
      {query.data ? (
        <div className={`space-y-6 transition-opacity ${query.isPlaceholderData ? "opacity-50" : ""}`} aria-busy={query.isPlaceholderData}>
          <ProcessHealth flows={query.data.process_health ?? []} />
          <ObjectionBreakdown
            categories={query.data.objection_categories ?? []}
            competitors={query.data.competitor_mentions}
            sampleLimited={query.data.sample_limited === true}
            emptyText={period === "week" ? undefined : p.hosObjectionsEmptyPeriod}
          />
        </div>
      ) : null}
      <section aria-labelledby="hos-process-define" className="space-y-4" id="playbooks">
        <h2 id="hos-process-define" className={THEME_TOKENS.typography.sectionTitle}>{p.hosProcessDefineHeading}</h2>
        <PlaybooksSection />
      </section>
    </main>
  );
}
