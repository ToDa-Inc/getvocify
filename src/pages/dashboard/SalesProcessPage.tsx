import { useState } from "react";
import { useAuth } from "@/features/auth";
import { HosFilters, HosPageHeader } from "@/features/head-of-sales/HosFilters";
import { ProcessHealth } from "@/features/head-of-sales/ProcessHealth";
import { useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import PlaybooksSection from "@/features/playbooks/components/PlaybooksSection";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { HOS_DEFAULT_PERIOD, type HosPeriod, type HosSalesRole } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { showProcessAnalytics } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * Proceso de venta: the process first (what Vocify checks on every call), then whether it is
 * working. The analytics only appear once there are scored calls to read, with their filters.
 */
export default function SalesProcessPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const [period, setPeriod] = useState<HosPeriod>(HOS_DEFAULT_PERIOD);
  const [salesRole, setSalesRole] = useState<HosSalesRole>("all");
  const query = useTeamAdherence(period, salesRole);
  const filtered = period !== HOS_DEFAULT_PERIOD || salesRole !== "all";
  const analytics = showProcessAnalytics(query.data, filtered);

  return (
    <main className={`max-w-5xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <HosPageHeader title={p.hosProcessTitle} subtitle={p.hosProcessPageSubtitle} />
      <section aria-label={p.pb2.sectionTitle} id="playbooks">
        <PlaybooksSection />
      </section>
      {analytics && query.data ? (
        <section aria-labelledby="hos-process-working" className={`space-y-4 ${THEME_TOKENS.motion.fadeIn}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="hos-process-working" className={THEME_TOKENS.typography.sectionTitle}>{p.pb2.analyticsTitle}</h2>
            <HosFilters
              period={period}
              salesRole={salesRole}
              onPeriod={setPeriod}
              onSalesRole={setSalesRole}
              showRoles={Boolean(user?.company?.features?.includes("SALES_ROLES_ENABLED"))}
            />
          </div>
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
        </section>
      ) : null}
    </main>
  );
}
