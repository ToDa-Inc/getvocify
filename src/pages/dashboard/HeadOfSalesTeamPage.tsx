import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { HosFilters } from "@/features/head-of-sales/HosFilters";
import { TeamCoaching } from "@/features/head-of-sales/TeamCoaching";
import { HOS_DEFAULT_PERIOD, type HosPeriod, type HosSalesRole } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { usesRepHome } from "@/lib/nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * Head of Sales Equipo (docs/superpowers/plans/2026-10-13-coaching-v2-comercial-y-conclusiones.md §3):
 * do they follow the playbook, does it work, why we lose. One plane, like the reps' Coaching.
 */
export default function HeadOfSalesTeamPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const [period, setPeriod] = useState<HosPeriod>(HOS_DEFAULT_PERIOD);
  const [salesRole, setSalesRole] = useState<HosSalesRole>("all");
  const features = user?.company?.features ?? [];
  // Edge to edge within the page's margins and 12px in, like Inicio and Coaching.
  return (
    <main className={`w-full space-y-10 ${THEME_TOKENS.motion.fadeIn}`}>
      <header className="flex flex-wrap items-center justify-between gap-4 px-3">
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.teamTitle}</h1>
        <div className="flex flex-wrap items-center gap-3">
          {/* T13: a Head of Sales who also sells keeps a way to their own day, off the menu. */}
          {usesRepHome(user?.company) ? (
            <Button asChild variant="quiet" size="text">
              <Link to="/dashboard/today">{p.hosGoToToday}</Link>
            </Button>
          ) : null}
          <HosFilters
            period={period}
            salesRole={salesRole}
            onPeriod={setPeriod}
            onSalesRole={setSalesRole}
            showRoles={features.includes("SALES_ROLES_ENABLED")}
          />
        </div>
      </header>
      <TeamCoaching period={period} salesRole={salesRole} />
    </main>
  );
}
